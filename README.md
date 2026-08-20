# Live Race Strategy Agent

A pit strategy assistant that replays real Formula 1 telemetry lap by lap, answering on every lap whether the car should pit now.

**Live demo:** [f1-race-strategy-agent.vercel.app](https://f1-race-strategy-agent.vercel.app)

Backend streams cached [OpenF1](https://openf1.org/) data over SSE at a configurable pace; a decision agent (rule-based, or a real Claude tool-use agent) reasons over tire degradation, gaps, weather, and track status; a React dashboard shows the verdict and the full reasoning trace behind it.

## Features

- Historical race replay over Server-Sent Events, at 1x–20x speed
- Tire degradation curves fitted per compound from real lap-time data (not hardcoded)
- Two interchangeable decision agents, switchable at runtime:
  - Rule-based: explicit logic (accumulated wear vs. undercut window, stale-tire check, caution-period discount, rain-on-slicks override, rival tire comparison)
  - Claude tool-use agent: calls `get_tire_degradation_estimate`, `get_gap_to_rivals`, `get_weather`, `get_track_status` before submitting a verdict; falls back to the rule-based agent if no key is available or a call fails. Each visitor supplies their own Anthropic API key (kept in their browser's localStorage, sent per-request as a header) — a deployed instance never uses one shared key on anyone's behalf
- Accuracy scorecard: replays every driver's race and checks agent PIT calls against real pit stops
- Dashboard with live verdict, gap/weather panel, degradation chart, full per-lap reasoning trace, and a lap history table — click any lap to inspect it

## Architecture

```
backend/
  app/
    ingest.py        pulls a session from OpenF1, caches to backend/data/<session_key>/*.json
    degradation.py    fits lap_time = intercept + slope * tire_age per compound
    agent.py          rule-based decision logic
    llm_agent.py      Claude tool-use agent (same output shape as agent.py)
    replay.py         reconstructs per-lap race state and streams it
    scorecard.py      compares agent PIT calls against real pit stops
    main.py           FastAPI app (sessions, degradation, scorecard, replay stream, health)
  data/<session_key>/  cached OpenF1 JSON, committed — regenerate/extend with ingest.py

frontend/
  src/
    App.jsx                    top-level state, SSE lifecycle
    components/
      Controls.jsx              session / driver / speed / agent picker
      DecisionHeader.jsx        verdict + current lap stats
      GapPanel.jsx              gaps, rival tires, conditions
      DegradationChart.jsx      fitted degradation curves
      ReasoningTrace.jsx        full per-lap reasoning log
      LapHistory.jsx            lap-by-lap table
      Scorecard.jsx             agent accuracy vs. real pit stops
```

## Getting started

### Backend

Requires a standard CPython 3.10+ build (an MSYS2/mingw Python won't have PyPI wheels for numpy/pydantic-core).

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m app.ingest 9523  # caches 2024 Monaco GP (session_key 9523)
uvicorn app.main:app --reload --port 8000
```

To ingest a different race, find a `session_key` at
`https://api.openf1.org/v1/sessions?year=2024&session_name=Race`, run `python -m app.ingest <session_key>`, and restart.

### Frontend

Requires Node 16+.

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Claude agent (optional)

Check "Claude reasoning" in the UI and paste an API key into the field that appears — it's stored in your browser's localStorage and sent to the backend as a request header, never as a URL parameter or logged server-side. Get a key at [console.anthropic.com](https://console.anthropic.com/settings/keys).

For local development, you can skip re-entering a key every time by setting one server-side as a fallback:

```bash
cd backend
cp .env.example .env
# set ANTHROPIC_API_KEY=sk-ant-... in .env
```

This fallback is only used when a request doesn't carry its own key — **don't set it on a public deployment**, or every visitor's Claude usage bills to that one key. With Claude mode on, replay pace is set by model latency rather than the speed slider, and each lap costs a small number of tokens. The scorecard always uses the rule-based agent, since it evaluates every driver's full race on load.

## Deployment

The repo includes `render.yaml` for the backend. Both steps are done through each provider's own dashboard — deploying isn't something that can be scripted end-to-end without your account credentials.

**Backend (Render):**
1. [dashboard.render.com](https://dashboard.render.com) → New → Blueprint → connect this GitHub repo. Render reads `render.yaml` and configures the service automatically (root directory `backend`, build/start commands, Python version).
2. Leave `ANTHROPIC_API_KEY` unset on the service — Claude mode works entirely from visitor-supplied keys, and setting one here would let every visitor's usage bill to it.
3. Once deployed, note the service URL (`https://<name>.onrender.com`).

**Frontend (Vercel):**
1. [vercel.com/new](https://vercel.com/new) → import this repo.
2. Set the project's Root Directory to `frontend`.
3. Add an environment variable `VITE_API_BASE` set to the Render URL from above.
4. Deploy.

Render's free tier spins down after inactivity — the first request after idle can take ~30-60s to wake it back up.

## Known limitations

- The default session (2024 Monaco GP) has near-zero fitted degradation — fuel burn-off (~0.03–0.06s/lap) outweighs Monaco's low tire wear, so the agent correctly avoids tire-based PIT calls there. For a session with clearer tire-cliff behavior, ingest Bahrain (`9472`) or Spain (`9539`).
- The scorecard's recall percentage reflects the rule-based agent only.
- Gap/rival data is derived from the nearest `intervals` sample to each lap's timestamp, not sub-second telemetry — accurate to within a few seconds.

## Roadmap

- [x] Historical replay over SSE with configurable speed
- [x] Degradation curves fitted from real lap data
- [x] Rule-based agent with full reasoning trace
- [x] Claude tool-use agent with rule-based fallback
- [x] Accuracy scorecard against real pit stops
- [x] Weather and rival-tire context in the reasoning trace
- [x] Per-user Claude API keys, entered in the browser, never stored server-side
- [x] Deployed instance (frontend on Vercel, backend on Render — see Deployment above)

## Data

Race data from the free [OpenF1 API](https://openf1.org/). Not affiliated with Formula 1, FIA, or Liberty Media.

## License

MIT
