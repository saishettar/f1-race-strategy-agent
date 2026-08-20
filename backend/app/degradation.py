"""
Fits a per-compound tire degradation curve (lap time vs tire age) from real
race lap data, so the agent can reason about "how much is this tire falling
off right now" instead of using made-up numbers.
"""
import json
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(session_key: int, name: str) -> list:
    return json.loads((DATA_DIR / str(session_key) / f"{name}.json").read_text(encoding="utf-8"))


def build_training_set(session_key: int) -> dict:
    """Returns {compound: [(tire_age, lap_duration), ...]} with pit in/out
    laps and stint outliers (safety car, traffic, lockups) removed."""
    laps = _load(session_key, "laps")
    stints = _load(session_key, "stints")
    pits = _load(session_key, "pit")

    laps_by_driver_lap = {}
    for lap in laps:
        if lap["lap_duration"] is None:
            continue
        laps_by_driver_lap[(lap["driver_number"], lap["lap_number"])] = lap

    in_lap = {(p["driver_number"], p["lap_number"]) for p in pits}

    samples_by_compound: dict[str, list[tuple[int, float]]] = {}

    for stint in stints:
        driver = stint["driver_number"]
        compound = stint["compound"]
        lap_start = stint["lap_start"]
        lap_end = stint["lap_end"]
        age0 = stint["tyre_age_at_start"]

        if lap_start is None or lap_end is None:
            continue  # driver did not start / retired before this stint began

        stint_durations = []
        stint_laps = []
        for lap_number in range(lap_start, lap_end + 1):
            key = (driver, lap_number)
            lap = laps_by_driver_lap.get(key)
            if lap is None:
                continue
            if lap.get("is_pit_out_lap"):
                continue
            if key in in_lap:
                continue
            stint_laps.append((lap_number, lap["lap_duration"]))
            stint_durations.append(lap["lap_duration"])

        if len(stint_durations) < 3:
            continue

        median = float(np.median(stint_durations))
        bucket = samples_by_compound.setdefault(compound, [])
        for lap_number, duration in stint_laps:
            if duration > median * 1.10:
                continue  # safety car / VSC / traffic outlier
            age = age0 + (lap_number - lap_start)
            bucket.append((age, duration))

    return samples_by_compound


class DegradationModel:
    """Linear fit per compound: lap_time = intercept + slope * tire_age."""

    def __init__(self, session_key: int):
        self.session_key = session_key
        self.curves: dict[str, dict] = {}
        samples_by_compound = build_training_set(session_key)

        for compound, samples in samples_by_compound.items():
            if len(samples) < 5:
                continue
            ages = np.array([s[0] for s in samples], dtype=float)
            times = np.array([s[1] for s in samples], dtype=float)
            slope, intercept = np.polyfit(ages, times, 1)
            self.curves[compound] = {
                "slope": float(slope),
                "intercept": float(intercept),
                "n_samples": len(samples),
                "max_age_observed": int(ages.max()),
            }

    def compounds(self) -> list:
        return list(self.curves.keys())

    def predicted_lap_time(self, compound: str, tire_age: int) -> float | None:
        curve = self.curves.get(compound)
        if curve is None:
            return None
        return curve["intercept"] + curve["slope"] * tire_age

    def falloff_rate(self, compound: str) -> float:
        """Degradation rate in seconds/lap. Falls back to a conservative
        generic estimate if this compound wasn't observed enough."""
        curve = self.curves.get(compound)
        if curve is None:
            return 0.05
        return curve["slope"]

    def summary(self) -> dict:
        return self.curves


if __name__ == "__main__":
    model = DegradationModel(9523)
    for compound, curve in model.summary().items():
        print(f"{compound:8s} slope={curve['slope']:+.4f} s/lap  "
              f"intercept={curve['intercept']:.2f}s  n={curve['n_samples']}  "
              f"max_age_seen={curve['max_age_observed']}")
