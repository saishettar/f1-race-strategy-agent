import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

load_dotenv()

from app.degradation import DegradationModel
from app.replay import DATA_DIR, ReplayEngine, SessionData
from app.scorecard import compute_scorecard

app = FastAPI(title="Live Race Strategy Agent")

_anthropic_client = None
if os.environ.get("ANTHROPIC_API_KEY"):
    from anthropic import AsyncAnthropic
    _anthropic_client = AsyncAnthropic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_SESSION_KEY = 9523


def available_sessions() -> list[int]:
    if not DATA_DIR.exists():
        return []
    return sorted(int(p.name) for p in DATA_DIR.iterdir() if p.is_dir() and p.name.isdigit())


@app.get("/api/sessions")
def list_sessions():
    sessions = []
    for key in available_sessions():
        data = SessionData(key)
        meta = json.loads((DATA_DIR / str(key) / "sessions.json").read_text())[0]
        sessions.append({
            "session_key": key,
            "circuit": meta.get("circuit_short_name"),
            "country": meta.get("country_name"),
            "year": meta.get("year"),
            "date": meta.get("date_start"),
            "drivers": [
                {
                    "number": d["driver_number"],
                    "name": d["full_name"],
                    "team": d["team_name"],
                    "team_colour": d["team_colour"],
                }
                for d in data.drivers.values()
            ],
        })
    return sessions


@app.get("/api/degradation")
def degradation(session_key: int = DEFAULT_SESSION_KEY):
    model = DegradationModel(session_key)
    return model.summary()


@app.get("/api/replay/stream")
async def replay_stream(
    session_key: int = Query(DEFAULT_SESSION_KEY),
    driver_number: int = Query(1),
    speed: float = Query(2.0, gt=0, le=1000),
    use_llm: bool = Query(False),
):
    engine = ReplayEngine(session_key, driver_number, speed=speed, use_llm=use_llm, llm_client=_anthropic_client)

    async def event_source():
        start_payload = {"driver": engine.driver_info(), "llm_active": use_llm and _anthropic_client is not None}
        yield f"event: session_start\ndata: {json.dumps(start_payload)}\n\n"
        try:
            async for event in engine.stream():
                yield f"event: lap_update\ndata: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            return
        yield f"event: session_end\ndata: {{}}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/scorecard")
def scorecard(session_key: int = DEFAULT_SESSION_KEY, window: int = 2):
    return compute_scorecard(session_key, window=window)


@app.get("/api/health")
def health():
    return {"status": "ok", "sessions_cached": available_sessions(), "llm_available": _anthropic_client is not None}
