"""Eval target wrapper for decide_llm -- flattens LapContext/DegradationModel
construction into simple, YAML-serializable kwargs so iris-eval can call it
directly as `eval.target:pit_decision`.

DegradationModel is built from real cached session data in backend/data/
(not a live network call), so this is repeatable without external state.
"""
import os

from anthropic import AsyncAnthropic

from app.agent import LapContext
from app.degradation import DegradationModel
from app.llm_agent import decide_llm

_model_cache: dict[int, DegradationModel] = {}


def _get_model(session_key: int) -> DegradationModel:
    if session_key not in _model_cache:
        _model_cache[session_key] = DegradationModel(session_key)
    return _model_cache[session_key]


async def pit_decision(
    session_key: int,
    lap_number: int,
    compound: str,
    tire_age: int,
    gap_ahead: float | None = None,
    gap_behind: float | None = None,
    gap_to_leader: float | None = None,
    rival_ahead_compound: str | None = None,
    rival_ahead_tire_age: int | None = None,
    rival_ahead_number: int | None = None,
    track_temp: float | None = None,
    air_temp: float | None = None,
    rainfall: bool = False,
    flag: str | None = None,
) -> str:
    ctx = LapContext(
        driver_number=1,
        lap_number=lap_number,
        compound=compound,
        tire_age=tire_age,
        gap_ahead=gap_ahead,
        gap_behind=gap_behind,
        gap_to_leader=gap_to_leader,
        flag=flag,
        rival_ahead_compound=rival_ahead_compound,
        rival_ahead_tire_age=rival_ahead_tire_age,
        rival_ahead_number=rival_ahead_number,
        track_temp=track_temp,
        air_temp=air_temp,
        rainfall=rainfall,
    )
    model = _get_model(session_key)
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    decision = await decide_llm(ctx, model, client)
    return f"{decision.action}: {' '.join(decision.reasoning)}"
