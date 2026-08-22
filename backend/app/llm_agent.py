"""
Real Claude tool-use agent: same job as agent.decide() (turn a LapContext
into a PIT / STAY OUT verdict with a reasoning trace), but instead of
hand-coded rules, an actual Claude model reasons over the situation and
decides what data it needs by calling tools — degradation estimates, gap
info, weather — before committing to a verdict via a final `submit_decision`
tool call.

Falls back to the rule-based agent (with a note explaining why) if no API
key is configured or the API call fails, so the app still works out of the
box for anyone cloning the repo without Anthropic credentials.
"""
import json
import os

from iris_otel import observe, trace_llm_call
from iris_otel.presets import anthropic_finish_reason, anthropic_usage

from app.agent import LapContext, PitDecision, decide as decide_rule_based
from app.degradation import DegradationModel

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ROUNDS = 6

TOOLS = [
    {
        "name": "get_tire_degradation_estimate",
        "description": (
            "Look up the fitted tire degradation rate for a compound at this circuit, "
            "based on real lap times from this race. Returns seconds/lap falloff, how "
            "many real laps the fit is based on, and the longest stint anyone has run "
            "on that compound so far."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "compound": {"type": "string", "enum": ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]},
                "tire_age": {"type": "integer", "description": "Current age of the tire in laps"},
            },
            "required": ["compound", "tire_age"],
        },
    },
    {
        "name": "get_gap_to_rivals",
        "description": (
            "Get the current time gap to the car ahead, the car behind, and the race "
            "leader, plus what compound/tire age the car directly ahead is on."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather",
        "description": "Get current track temperature, air temperature, and whether it's raining.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_track_status",
        "description": "Get the current track flag status (green/yellow/red/safety car).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "submit_decision",
        "description": (
            "Submit your final pit strategy call. Call this exactly once, after you've "
            "gathered whatever information you need."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["PIT", "STAY OUT"]},
                "reasoning": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "3-6 short sentences, race-engineer radio style, walking through "
                        "why — e.g. 'Tires are 0.4s/lap off the pace now.' 'Gap behind is "
                        "1.2 seconds, they're in undercut range.' 'Box, box.'"
                    ),
                },
            },
            "required": ["action", "reasoning"],
        },
    },
]


def _execute_tool(name: str, ctx: LapContext, model: DegradationModel) -> dict:
    if name == "get_tire_degradation_estimate":
        curve = model.curves.get(ctx.compound)
        return {
            "slope_s_per_lap": model.falloff_rate(ctx.compound),
            "based_on_real_laps": curve["n_samples"] if curve else 0,
            "longest_stint_observed_this_race": curve["max_age_observed"] if curve else None,
            "note": "Negative slope means lap times are getting faster (fuel burn-off "
                    "outweighing tire wear) — common at low-degradation circuits.",
        }
    if name == "get_gap_to_rivals":
        return {
            "gap_ahead_s": ctx.gap_ahead,
            "gap_behind_s": ctx.gap_behind,
            "gap_to_leader_s": ctx.gap_to_leader,
            "rival_ahead": {
                "driver_number": ctx.rival_ahead_number,
                "compound": ctx.rival_ahead_compound,
                "tire_age": ctx.rival_ahead_tire_age,
            } if ctx.rival_ahead_number else None,
        }
    if name == "get_weather":
        return {
            "track_temp_c": ctx.track_temp,
            "air_temp_c": ctx.air_temp,
            "raining": ctx.rainfall,
        }
    if name == "get_track_status":
        return {"flag": ctx.flag or "GREEN"}
    return {"error": f"unknown tool {name}"}


def _fallback(ctx: LapContext, model: DegradationModel, reason: str) -> PitDecision:
    decision = decide_rule_based(ctx, model)
    decision.reasoning = [f"[Claude unavailable: {reason} — falling back to rule-based agent]"] + decision.reasoning
    return decision


@trace_llm_call(model=MODEL, extract_usage=anthropic_usage, extract_finish_reasons=anthropic_finish_reason)
async def _call_claude(client, **kwargs):
    return await client.messages.create(**kwargs)


async def decide_llm(ctx: LapContext, model: DegradationModel, client) -> PitDecision:
    if client is None:
        return _fallback(ctx, model, "no ANTHROPIC_API_KEY configured")

    with observe("invoke_agent", **{"gen_ai.agent.name": "f1-pit-strategy"}):
        system = (
            "You are a Formula 1 race strategist making a live pit call for your own car. "
            f"It is lap {ctx.lap_number}. Your car is on {ctx.compound} tires, {ctx.tire_age} "
            "laps old. Use the available tools to check tire degradation, gaps to rivals, "
            "weather, and track status before deciding — don't guess at numbers you can look "
            "up. When you've gathered what you need, call submit_decision exactly once with "
            "your verdict and a short step-by-step reasoning trail in race-engineer radio style."
        )
        messages = [{"role": "user", "content": "What's the call — pit this lap, or stay out?"}]

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = await _call_claude(
                    client,
                    model=MODEL,
                    max_tokens=1024,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                )

                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                if not tool_use_blocks:
                    return _fallback(ctx, model, "model didn't call submit_decision")

                submit = next((b for b in tool_use_blocks if b.name == "submit_decision"), None)
                if submit is not None:
                    action = submit.input.get("action", "STAY OUT")
                    reasoning = submit.input.get("reasoning", [])
                    return PitDecision(
                        action=action,
                        reasoning=list(reasoning),
                        falloff_rate=model.falloff_rate(ctx.compound),
                    )

                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in tool_use_blocks:
                    with observe("execute_tool", **{"gen_ai.tool.name": block.name}):
                        tool_output = _execute_tool(block.name, ctx, model)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_output),
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

            return _fallback(ctx, model, "exceeded max tool-call rounds without a decision")
        except Exception as e:
            return _fallback(ctx, model, f"API error ({type(e).__name__})")
