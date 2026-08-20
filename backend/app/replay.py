"""
Turns a cached historical session into a live-feeling stream: iterates one
driver's race lap by lap, in lap order, reconstructing what a race engineer
would have known at the moment each lap ended (tire age, gap ahead/behind,
track status), running the pit/stay-out agent, and yielding one event per
lap with a real (or sped-up) delay between events.
"""
import asyncio
import bisect
import json
from datetime import datetime
from pathlib import Path

from app.agent import LapContext, decide
from app.degradation import DegradationModel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(session_key: int, name: str) -> list:
    return json.loads((DATA_DIR / str(session_key) / f"{name}.json").read_text(encoding="utf-8"))


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class SessionData:
    """Loads and indexes one cached session for fast per-lap lookups."""

    def __init__(self, session_key: int):
        self.session_key = session_key
        self.drivers = {d["driver_number"]: d for d in _load(session_key, "drivers")}
        self.laps = _load(session_key, "laps")
        self.stints = _load(session_key, "stints")
        self.pits = _load(session_key, "pit")
        self.race_control = _load(session_key, "race_control")

        intervals = _load(session_key, "intervals")
        self.intervals_by_driver: dict[int, list[tuple[datetime, dict]]] = {}
        for rec in intervals:
            if rec.get("date") is None:
                continue
            dt = _parse_dt(rec["date"])
            self.intervals_by_driver.setdefault(rec["driver_number"], []).append((dt, rec))
        for records in self.intervals_by_driver.values():
            records.sort(key=lambda x: x[0])
        self._interval_keys = {
            driver: [dt for dt, _ in records]
            for driver, records in self.intervals_by_driver.items()
        }

        self.pit_laps = {(p["driver_number"], p["lap_number"]) for p in self.pits}

        weather = _load(session_key, "weather")
        self._weather: list[tuple[datetime, dict]] = sorted(
            ((_parse_dt(rec["date"]), rec) for rec in weather if rec.get("date")),
            key=lambda x: x[0],
        )
        self._weather_keys = [dt for dt, _ in self._weather]

        self.flagged_laps: dict[int, str] = {}
        caution_flags = {"RED", "YELLOW", "DOUBLE YELLOW"}
        for rc in self.race_control:
            lap_number = rc.get("lap_number")
            flag = rc.get("flag")
            msg = (rc.get("message") or "").upper()
            if lap_number is None:
                continue
            if flag in caution_flags:
                if "SAFETY CAR" in msg:
                    self.flagged_laps[lap_number] = "SAFETY CAR"
                elif flag == "DOUBLE YELLOW":
                    self.flagged_laps[lap_number] = "YELLOW"
                else:
                    self.flagged_laps[lap_number] = flag

    def nearest_interval(self, driver_number: int, at: datetime) -> dict | None:
        keys = self._interval_keys.get(driver_number)
        if not keys:
            return None
        i = bisect.bisect_right(keys, at) - 1
        if i < 0:
            i = 0
        return self.intervals_by_driver[driver_number][i][1]

    def _ranked_by_gap(self, at: datetime) -> list[tuple[float, int]]:
        """Every driver ranked by nearest gap_to_leader sample at `at`."""
        ranked = []
        for other_driver in self.intervals_by_driver:
            rec = self.nearest_interval(other_driver, at)
            if rec is None or rec.get("gap_to_leader") is None:
                continue
            gap = rec["gap_to_leader"]
            if isinstance(gap, str):  # e.g. "+1 LAP"
                continue
            ranked.append((gap, other_driver))
        ranked.sort()
        return ranked

    def gap_behind(self, driver_number: int, at: datetime) -> float | None:
        """Time delta to whichever driver sits directly behind on track."""
        ranked = self._ranked_by_gap(at)
        for idx, (gap, drv) in enumerate(ranked):
            if drv == driver_number:
                if idx + 1 < len(ranked):
                    return round(ranked[idx + 1][0] - gap, 3)
                return None
        return None

    def rival_ahead(self, driver_number: int, at: datetime, lap_number: int) -> dict | None:
        """Identity + tire info of whichever driver sits directly ahead on
        track, approximated using their compound/age at the same lap number
        (they're close together on track, so this is a reasonable stand-in)."""
        ranked = self._ranked_by_gap(at)
        for idx, (gap, drv) in enumerate(ranked):
            if drv == driver_number:
                if idx == 0:
                    return None  # leader — nobody ahead
                rival_number = ranked[idx - 1][1]
                rival_compound_age = self.compound_and_age(rival_number, lap_number)
                return {
                    "driver_number": rival_number,
                    "name": self.drivers.get(rival_number, {}).get("full_name"),
                    "compound": rival_compound_age[0] if rival_compound_age else None,
                    "tire_age": rival_compound_age[1] if rival_compound_age else None,
                }
        return None

    def nearest_weather(self, at: datetime) -> dict | None:
        if not self._weather_keys:
            return None
        i = bisect.bisect_right(self._weather_keys, at) - 1
        if i < 0:
            i = 0
        return self._weather[i][1]

    def compound_and_age(self, driver_number: int, lap_number: int) -> tuple[str, int] | None:
        for stint in self.stints:
            if stint["driver_number"] != driver_number:
                continue
            if stint["lap_start"] is None or stint["lap_end"] is None:
                continue
            if stint["lap_start"] <= lap_number <= stint["lap_end"]:
                age = stint["tyre_age_at_start"] + (lap_number - stint["lap_start"])
                return stint["compound"], age
        return None

    def driver_laps(self, driver_number: int) -> list[dict]:
        laps = [
            lap for lap in self.laps
            if lap["driver_number"] == driver_number and lap["lap_duration"] is not None
        ]
        laps.sort(key=lambda l: l["lap_number"])
        return laps


def build_lap_context(data: SessionData, driver_number: int, lap: dict) -> LapContext:
    """Reconstructs what a race engineer would have known at the moment this
    lap ended: tire age, gaps, rival's tires, weather, track status."""
    lap_number = lap["lap_number"]
    end_time = _parse_dt(lap["date_start"])
    compound_age = data.compound_and_age(driver_number, lap_number)
    compound, tire_age = compound_age if compound_age else ("UNKNOWN", 0)

    own_interval = data.nearest_interval(driver_number, end_time)
    gap_ahead = own_interval.get("interval") if own_interval else None
    gap_to_leader = own_interval.get("gap_to_leader") if own_interval else None
    if isinstance(gap_ahead, str):
        gap_ahead = None
    if isinstance(gap_to_leader, str):
        gap_to_leader = None
    gap_behind = data.gap_behind(driver_number, end_time)
    rival = data.rival_ahead(driver_number, end_time, lap_number)
    weather = data.nearest_weather(end_time)
    flag = data.flagged_laps.get(lap_number)

    return LapContext(
        driver_number=driver_number,
        lap_number=lap_number,
        compound=compound,
        tire_age=tire_age,
        gap_ahead=gap_ahead,
        gap_behind=gap_behind,
        gap_to_leader=gap_to_leader,
        flag=flag,
        rival_ahead_compound=rival.get("compound") if rival else None,
        rival_ahead_tire_age=rival.get("tire_age") if rival else None,
        rival_ahead_number=rival.get("driver_number") if rival else None,
        track_temp=weather.get("track_temperature") if weather else None,
        air_temp=weather.get("air_temperature") if weather else None,
        rainfall=bool(weather.get("rainfall")) if weather else False,
    )


def _build_event(data: SessionData, driver_number: int, lap: dict, ctx: LapContext, decision) -> dict:
    driver_info = data.drivers.get(driver_number, {})
    rival = None
    if ctx.rival_ahead_number is not None:
        rival = {
            "driver_number": ctx.rival_ahead_number,
            "compound": ctx.rival_ahead_compound,
            "tire_age": ctx.rival_ahead_tire_age,
        }
    return {
        "type": "lap_update",
        "driver": {
            "number": driver_number,
            "name": driver_info.get("full_name"),
            "team": driver_info.get("team_name"),
            "team_colour": driver_info.get("team_colour"),
        },
        "lap_number": ctx.lap_number,
        "lap_duration": lap["lap_duration"],
        "compound": ctx.compound,
        "tire_age": ctx.tire_age,
        "gap_ahead": ctx.gap_ahead,
        "gap_behind": ctx.gap_behind,
        "gap_to_leader": ctx.gap_to_leader,
        "flag": ctx.flag,
        "pit_this_lap": (driver_number, ctx.lap_number) in data.pit_laps,
        "rival_ahead": rival,
        "weather": {
            "track_temp": ctx.track_temp,
            "air_temp": ctx.air_temp,
            "rainfall": ctx.rainfall,
        },
        "decision": {
            "action": decision.action,
            "reasoning": decision.reasoning,
            "falloff_rate": decision.falloff_rate,
        },
    }


def evaluate_driver_laps(data: SessionData, model: DegradationModel, driver_number: int) -> list[dict]:
    """Pure (no sleep, no I/O) per-lap reconstruction + rule-based agent
    decision for one driver's whole race. Shared by the live SSE replay
    (rule-based mode) and the scorecard, which always uses the fast
    rule-based agent even when the live replay is using Claude."""
    events = []
    for lap in data.driver_laps(driver_number):
        ctx = build_lap_context(data, driver_number, lap)
        decision = decide(ctx, model)
        events.append(_build_event(data, driver_number, lap, ctx, decision))
    return events


class ReplayEngine:
    def __init__(self, session_key: int, driver_number: int, speed: float = 1.0,
                 use_llm: bool = False, llm_client=None):
        self.data = SessionData(session_key)
        self.driver_number = driver_number
        self.speed = speed  # events per second-ish; higher = faster demo pace
        self.model = DegradationModel(session_key)
        self.use_llm = use_llm
        self.llm_client = llm_client  # AsyncAnthropic instance, or None (surfaces a fallback note)

    def driver_info(self) -> dict:
        return self.data.drivers.get(self.driver_number, {})

    async def stream(self):
        if not self.use_llm:
            events = evaluate_driver_laps(self.data, self.model, self.driver_number)
            for event in events:
                yield event
                await asyncio.sleep(1.0 / self.speed)
            return

        from app.llm_agent import decide_llm  # local import: keeps rule-based path anthropic-free

        for lap in self.data.driver_laps(self.driver_number):
            ctx = build_lap_context(self.data, self.driver_number, lap)
            decision = await decide_llm(ctx, self.model, self.llm_client)
            yield _build_event(self.data, self.driver_number, lap, ctx, decision)
            # LLM latency already paces this; only add extra delay if speed is low
            await asyncio.sleep(max(0.0, 1.0 / self.speed - 0.05))
