# Live Race Strategy Agent

Replays a real Formula 1 race, lap by lap, and asks on every lap: **should we pit now?**

It's not a static notebook — it's a FastAPI backend that streams real [OpenF1](https://openf1.org/)
telemetry over SSE at whatever pace you choose, and a React dashboard that shows the
answer *and* the reasoning behind it, lap by lap, live.

> **Why "replay" instead of truly live?** OpenF1's free tier gives full historical data
> for every session since 2023, no signup required. Actual live/websocket data during a
> real race weekend needs a paid sponsorship tier and only works ~20 days a year. This
> project replays a real historical race in real time (or sped up) instead — same data
> shape, same reasoning pipeline, works any day, for any interviewer, forever. See
> [Pits n' Giggles](https://github.com/ryan-cunningham/PitsNGiggles) for another project
> that uses the same replay pattern for OpenF1 telemetry.

## What it does

1. **Ingests** historical race sessions from OpenF1 (laps, tire stints, gaps, pit
   stops, weather, race control flags) and caches them locally. Four 2024 races are
   cached by default: Bahrain, Australia, Monaco, and Spain.
2. **Fits a tire degradation curve per compound** from the real lap-time data in that
   session — not a made-up model. See [Known caveat](#known-caveat-monaco-is-a-bad-track-for-showing-degradation) below.
3. **Replays** one car's race lap by lap over Server-Sent Events, reconstructing what a
   race engineer would have known at the moment each lap ended: tire age, gap to the
   car ahead/behind and what they're on, track status (yellow/red/safety car), and
   weather (track/air temp, rain).
4. On every lap, a **decision agent** evaluates PIT vs. STAY OUT and produces a
   step-by-step reasoning trace — not just a verdict. Two implementations, switchable
   live from the UI:
   - **Rule-based** (default, always available): explicit hand-coded logic — accumulated
     tire wear vs. undercut window, stale-tire check, caution-period discount, rain-on-slicks
     safety override, rival tire comparison.
   - **Real Claude tool-use agent** (opt-in, needs an API key): an actual Claude model
     decides what it needs to know and calls tools — `get_tire_degradation_estimate`,
     `get_gap_to_rivals`, `get_weather`, `get_track_status` — before committing to a
     verdict via a final `submit_decision` tool call. See
     [Real Claude agent](#real-claude-agent) below.
5. A **scorecard** replays every driver's whole race through the (fast, rule-based)
   agent and checks its PIT calls against what actually happened — how many real pit
   stops did it call within N laps, and how many of its calls didn't match anything.
6. The frontend renders it all live: current verdict, gap panel + rival's tires +
   conditions, the fitted degradation curves with today's tire age plotted on them, a
   scrolling reasoning trace, a lap history table that flags where the real driver
   actually pitted, and the accuracy scorecard.

## Architecture

```
backend/
  app/
    ingest.py       one-off script: pulls a session from OpenF1, caches to backend/data/<session_key>/*.json
                     (retries with backoff on the free tier's rate limit, resumable)
    degradation.py  fits lap_time = intercept + slope * tire_age per compound (numpy polyfit),
                     with pit in/out laps and safety-car/traffic outliers filtered out
    agent.py        rule-based PIT / STAY OUT decision with an explicit reasoning trace
    llm_agent.py     real Claude tool-use agent — same PitDecision shape, falls back to
                     agent.py if no API key / the call fails
    replay.py       reconstructs per-lap race state from cached data (tires, gaps, rival
                     tires, weather, flags) and streams it; shared by both agents
    scorecard.py    compares every driver's agent PIT calls against real pit stops
    main.py         FastAPI app: /api/sessions, /api/degradation, /api/scorecard,
                     /api/replay/stream (SSE, ?use_llm=true for the Claude agent), /api/health
  data/<session_key>/   cached OpenF1 JSON (gitignored — regenerate with ingest.py)
  .env             ANTHROPIC_API_KEY goes here (gitignored) — see .env.example

frontend/
  src/
    api.js                fetch + SSE URL helpers
    App.jsx                top-level state, EventSource lifecycle
    components/
      Controls.jsx         session / driver / speed / Claude-mode picker
      DecisionHeader.jsx    big PIT NOW / STAY OUT verdict + current stats
      GapPanel.jsx          gap to car ahead (+ their tires) / behind / leader, conditions
      DegradationChart.jsx  fitted degradation curves, current tire age marked
      ReasoningTrace.jsx    scrolling step-by-step agent reasoning log
      LapHistory.jsx        lap-by-lap table, flags real pit laps for comparison
      Scorecard.jsx         headline recall % + per-driver PIT-call comparison
```

## Running it

**Backend** (Python 3.10+, standard CPython — not an MSYS2/mingw build, which lacks
PyPI wheels for numpy/pydantic-core):

```bash
cd backend
python -m venv venv
venv/Scripts/activate   # or venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m app.ingest 9523   # caches the 2024 Monaco GP race (session_key 9523)
uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 16+):

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

To replay a different race: find a `session_key` via
`https://api.openf1.org/v1/sessions?year=2024&session_name=Race`, run
`python -m app.ingest <session_key>`, restart the backend, and pick it from the
session dropdown.

## Real Claude agent

By default the app runs entirely on the rule-based agent — no API key needed. To turn
on the real Claude tool-use agent:

```bash
cd backend
cp .env.example .env
# edit .env, set ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload --port 8000   # restart to pick up the key
```

The "🤖 Real Claude reasoning" checkbox in the UI lights up once the backend reports a
key is configured (`GET /api/health` → `llm_available`). With it on, each lap's decision
comes from an actual tool-use loop (`backend/app/llm_agent.py`) instead of `agent.py`'s
hand-coded rules — the model calls tools to look up degradation, gaps, weather, and
track status itself, then submits a verdict + reasoning via a final `submit_decision`
tool call. Replay pace is then set by model latency (typically 1–3s/lap) rather than the
speed slider, and each lap costs a small number of API tokens. If the call fails for any
reason (no key, network error, rate limit), the response includes a
`[Claude unavailable: ...]` note and falls back to the rule-based verdict for that lap,
so the stream never just breaks.

The scorecard always uses the rule-based agent (running the real Claude agent across all
20 drivers × a full race on every page load would be slow and expensive) — it's meant to
validate the fast agent's calibration, not the Claude agent's.

## Known caveat: Monaco is a bad track for showing degradation

The fitted curves for the default session (2024 Monaco GP) come out **negative** —
lap times get *faster* as the tires age:

```
HARD     -0.041 s/lap
MEDIUM   -0.059 s/lap
SOFT     +0.029 s/lap   (only 32 samples — one short stint, noisy)
```

This is real, not a bug: Monaco has famously low thermal tire degradation, so fuel
burn-off (~0.03–0.06s/lap faster as the car gets lighter) outweighs tire wear over a
stint. The agent handles this correctly — it reasons "fuel burn-off is outweighing tire
wear at this circuit" and (correctly) almost never recommends pitting for tire reasons
at Monaco. Real Monaco strategy is track-position-driven, not tire-cliff-driven, and
that's what the reasoning trace shows.

For a demo with dramatic tire-cliff PIT calls, ingest a high-degradation race instead
(e.g. Bahrain or Spain) and switch to it in the session dropdown.

## Roadmap

- [x] Real OpenF1 data, cached and replayed lap-by-lap over SSE
- [x] Degradation curves fitted from real lap times, per compound
- [x] Rule-based PIT / STAY OUT agent with a full reasoning trace
- [x] Live dashboard: verdict, gaps, degradation chart, reasoning trace, lap history
- [x] Multiple cached sessions (Bahrain, Australia, Monaco, Spain), resumable ingestion
- [x] Accuracy scorecard: agent PIT calls vs. real pit stops, across the whole field
- [x] Weather and rival-tire context feeding the reasoning trace (rain-on-slicks safety
      override, overcut/undercut framed against what the car ahead is actually on)
- [x] Real Claude tool-use agent (`get_tire_degradation_estimate`, `get_gap_to_rivals`,
      `get_weather`, `get_track_status`, `submit_decision`), switchable live in the UI,
      with a graceful rule-based fallback
- [ ] Deploy: frontend on Vercel, backend on Render/Fly.io, for a clickable public demo

## Data

All race data via the free [OpenF1 API](https://openf1.org/). Not affiliated with
Formula 1, FIA, or Liberty Media.
