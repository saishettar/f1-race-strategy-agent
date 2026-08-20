"""
Rule-based "should we pit now?" decision engine.

This is deliberately written as an explicit, steppable reasoning trace
(rather than one opaque boolean expression) so it can later be swapped for
a real Claude tool-use agent without changing the shape of what the
frontend renders: a list of reasoning steps ending in a verdict.
"""
from dataclasses import dataclass, field

from app.degradation import DegradationModel

UNDERCUT_DEG_THRESHOLD = 0.02   # s/lap falloff considered "tires are measurably wearing"
UNDERCUT_WINDOW_BASE = 1.0      # seconds — floor of what counts as undercut range
UNDERCUT_WINDOW_SCALE = 20.0    # undercut_window = BASE + falloff * SCALE
STALE_TIRE_AGE_MARGIN = 3       # laps beyond the longest observed stint on this compound
PIT_LOSS_ESTIMATE = 22.0        # seconds, rough pit-lane loss

# Real fitted degradation slopes rarely exceed ~0.15s/lap even on high-wear tracks
# (see backend/app/degradation.py) — these thresholds are calibrated against the
# 2024 Bahrain/Australia/Spain/Monaco cached sessions, not the 0.3-0.5s/lap figures
# a naive guess would use.


@dataclass
class LapContext:
    driver_number: int
    lap_number: int
    compound: str
    tire_age: int
    gap_ahead: float | None       # seconds to car ahead (interval)
    gap_behind: float | None      # seconds to car behind
    gap_to_leader: float | None
    flag: str | None = None       # e.g. "YELLOW", "RED", "SAFETY CAR", None
    rival_ahead_compound: str | None = None
    rival_ahead_tire_age: int | None = None
    rival_ahead_number: int | None = None
    track_temp: float | None = None
    air_temp: float | None = None
    rainfall: bool = False


@dataclass
class PitDecision:
    action: str                   # "PIT" or "STAY OUT"
    reasoning: list[str] = field(default_factory=list)
    falloff_rate: float = 0.0


SLICK_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}


def decide(ctx: LapContext, model: DegradationModel) -> PitDecision:
    steps = []
    pit_reasons = []

    # Reason 0: rain on slicks is a safety issue, not a strategy trade-off —
    # this overrides everything else.
    weather_bits = []
    if ctx.track_temp is not None:
        weather_bits.append(f"track {ctx.track_temp:.0f}°C")
    if ctx.air_temp is not None:
        weather_bits.append(f"air {ctx.air_temp:.0f}°C")
    if weather_bits:
        steps.append(f"Conditions: {', '.join(weather_bits)}" + (", RAIN" if ctx.rainfall else ", dry") + ".")
    if ctx.rainfall and ctx.compound in SLICK_COMPOUNDS:
        steps.append(
            f"Rain detected while on {ctx.compound} slicks — this is a safety call, not a "
            "strategy trade-off. Grip is compromised regardless of tire age or gaps."
        )
        pit_reasons.append("wet_conditions")

    falloff = model.falloff_rate(ctx.compound)
    curve = model.curves.get(ctx.compound)

    if curve is not None:
        steps.append(
            f"Tire: {ctx.compound}, age {ctx.tire_age} laps. Fitted degradation model for "
            f"this compound at this circuit: {falloff:+.3f}s/lap "
            f"(from {curve['n_samples']} real laps, longest stint observed: "
            f"{curve['max_age_observed']} laps)."
        )
    else:
        steps.append(
            f"Tire: {ctx.compound}, age {ctx.tire_age} laps. No degradation data for this "
            f"compound at this circuit — using conservative default falloff {falloff:+.3f}s/lap."
        )

    # Reason 1: tire has accumulated enough real wear that an undercut is live.
    # Gated on tire_age too, not just the compound's average slope — a 2-lap-old
    # tire on a wearing compound hasn't actually lost meaningful time yet.
    cumulative_loss = max(falloff, 0.0) * ctx.tire_age
    if ctx.gap_ahead is None:
        steps.append("No car ahead on track (leader) — undercut logic does not apply.")
    elif falloff < UNDERCUT_DEG_THRESHOLD or cumulative_loss < 0.3:
        steps.append(
            f"Degradation ({falloff:+.2f}s/lap) x tire age ({ctx.tire_age}) = "
            f"~{cumulative_loss:.2f}s accumulated loss so far"
            + (" — fuel burn-off is outweighing tire wear at this circuit" if falloff < 0 else "")
            + "; not enough accumulated wear yet for an undercut to be worth it."
        )
    else:
        undercut_window = UNDERCUT_WINDOW_BASE + falloff * UNDERCUT_WINDOW_SCALE
        if ctx.gap_ahead <= undercut_window:
            steps.append(
                f"~{cumulative_loss:.2f}s of accumulated tire wear ({falloff:.2f}s/lap x "
                f"{ctx.tire_age} laps) and gap ahead ({ctx.gap_ahead:.1f}s) is within undercut "
                f"range (<= {undercut_window:.1f}s) — pitting now could jump the car ahead on "
                "fresher tires."
            )
            pit_reasons.append("undercut")
        else:
            steps.append(
                f"~{cumulative_loss:.2f}s of accumulated tire wear, but gap ahead "
                f"({ctx.gap_ahead:.1f}s) is beyond undercut range (<= {undercut_window:.1f}s) "
                "— no window yet."
            )

    # Reason 1b: what's the car directly ahead actually on? Context for the
    # undercut/overcut call above, not a separate trigger on its own.
    if ctx.rival_ahead_number is not None and ctx.rival_ahead_compound is not None:
        age_delta = ctx.rival_ahead_tire_age - ctx.tire_age
        if age_delta >= 3:
            steps.append(
                f"Car ahead (#{ctx.rival_ahead_number}) is on {ctx.rival_ahead_compound}, "
                f"{age_delta} laps older than ours — they're more likely to pit or fade first; "
                "an overcut (staying out and gaining track position while they box) is in play."
            )
        elif age_delta <= -3:
            steps.append(
                f"Car ahead (#{ctx.rival_ahead_number}) already has fresher tires "
                f"({ctx.rival_ahead_compound}, {-age_delta} laps younger than ours) — an "
                "undercut on them specifically buys less than usual since they don't share our "
                "wear problem."
            )
        else:
            steps.append(
                f"Car ahead (#{ctx.rival_ahead_number}) is on similar-age "
                f"{ctx.rival_ahead_compound} ({ctx.rival_ahead_tire_age} laps) — comparable wear, "
                "straightforward pace comparison."
            )

    # Reason 2: tire is older than anything observed on this compound this race.
    if curve is not None and ctx.tire_age >= curve["max_age_observed"] + STALE_TIRE_AGE_MARGIN:
        steps.append(
            f"Tire age ({ctx.tire_age}) is {ctx.tire_age - curve['max_age_observed']} laps "
            f"beyond the longest {ctx.compound} stint anyone ran in this race "
            f"({curve['max_age_observed']} laps) — into unknown wear territory."
        )
        pit_reasons.append("stale_tire")

    # Reason 3: a caution period makes the pit loss nearly free.
    if ctx.flag in ("YELLOW", "RED", "SAFETY CAR"):
        steps.append(
            f"Track status is {ctx.flag} — pit-lane time loss vs. the field is minimized "
            "right now, which lowers the bar for pitting."
        )
        pit_reasons.append("caution")

    # Reason 4: a car behind is closing fast enough to threaten an overcut/attack.
    if ctx.gap_behind is not None and ctx.gap_behind <= 1.0 and falloff > 0:
        steps.append(
            f"Car behind is only {ctx.gap_behind:.1f}s back while these tires are still "
            "degrading — defending on old tires is getting risky."
        )
        pit_reasons.append("under_attack")

    if pit_reasons:
        action = "PIT"
        steps.append(
            f"Verdict: PIT — triggered by {', '.join(pit_reasons)}. "
            f"Estimated pit-lane cost: ~{PIT_LOSS_ESTIMATE:.0f}s."
        )
    else:
        action = "STAY OUT"
        steps.append("Verdict: STAY OUT — no pit trigger fired this lap.")

    return PitDecision(action=action, reasoning=steps, falloff_rate=falloff)
