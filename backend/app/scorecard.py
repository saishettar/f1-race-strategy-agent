"""
Compares the agent's PIT calls against what actually happened in the race,
across every driver in a session. This is the headline "did the agent get
it right" number — the reasoning trace shows *why* on a single lap, this
shows how that judgment held up over a whole race.

Matching rule: an actual pit stop on lap L counts as "called" if the agent
recommended PIT on any lap in [L - window, L]. Calling it a lap or two early
counts as a hit (a real strategist wants the recommendation before the pit
wall commits, not exactly on it); calling it *after* the driver already
pitted does not, since the recommendation would have come too late to act on.

Real pit stops are distinguished from non-strategic ones (e.g. a red-flag
stoppage, which OpenF1 also reports as a "pit" record with a lane duration
in the thousands of seconds) via MAX_STRATEGIC_PIT_SECONDS.
"""
from app.degradation import DegradationModel
from app.replay import SessionData, evaluate_driver_laps

MATCH_WINDOW = 2
MAX_STRATEGIC_PIT_SECONDS = 120.0  # excludes red-flag / stopped-on-track artifacts


def strategic_pit_laps(data: SessionData, driver_number: int) -> list[int]:
    laps = []
    for pit in data.pits:
        if pit["driver_number"] != driver_number:
            continue
        duration = pit.get("pit_duration") or pit.get("lane_duration")
        if duration is None or duration > MAX_STRATEGIC_PIT_SECONDS:
            continue
        laps.append(pit["lap_number"])
    return sorted(laps)


def compute_scorecard(session_key: int, window: int = MATCH_WINDOW) -> dict:
    data = SessionData(session_key)
    model = DegradationModel(session_key)

    per_driver = []
    total_actual = 0
    total_matched = 0
    total_agent_calls = 0
    total_extra_calls = 0

    for driver_number, driver in data.drivers.items():
        actual_laps = strategic_pit_laps(data, driver_number)
        events = evaluate_driver_laps(data, model, driver_number)
        agent_pit_laps = [e["lap_number"] for e in events if e["decision"]["action"] == "PIT"]

        matched_actual = [
            al for al in actual_laps
            if any(0 <= al - pl <= window for pl in agent_pit_laps)
        ]
        extra_calls = [
            pl for pl in agent_pit_laps
            if not any(0 <= al - pl <= window for al in actual_laps)
        ]

        per_driver.append({
            "driver_number": driver_number,
            "name": driver.get("full_name"),
            "team": driver.get("team_name"),
            "actual_pit_laps": actual_laps,
            "agent_pit_laps": agent_pit_laps,
            "matched_pit_laps": matched_actual,
            "extra_call_laps": extra_calls,
        })

        total_actual += len(actual_laps)
        total_matched += len(matched_actual)
        total_agent_calls += len(agent_pit_laps)
        total_extra_calls += len(extra_calls)

    return {
        "session_key": session_key,
        "window": window,
        "total_actual_pit_stops": total_actual,
        "total_matched": total_matched,
        "recall_pct": round(100 * total_matched / total_actual, 1) if total_actual else None,
        "total_agent_pit_calls": total_agent_calls,
        "total_extra_calls": total_extra_calls,
        "per_driver": sorted(per_driver, key=lambda d: d["driver_number"]),
    }


if __name__ == "__main__":
    import json
    import sys
    session_key = int(sys.argv[1]) if len(sys.argv) > 1 else 9523
    result = compute_scorecard(session_key)
    print(f"session {session_key}: matched {result['total_matched']}/{result['total_actual_pit_stops']} "
          f"real pit stops ({result['recall_pct']}%), {result['total_extra_calls']} extra calls "
          f"out of {result['total_agent_pit_calls']} total PIT calls")
    for d in result["per_driver"]:
        if d["actual_pit_laps"] or d["agent_pit_laps"]:
            print(f"  #{d['driver_number']:2d} {d['name']:22s} actual={d['actual_pit_laps']} "
                  f"agent={d['agent_pit_laps']} matched={d['matched_pit_laps']}")
