import { useEffect, useRef, useState } from "react";
import "./App.css";
import { fetchSessions, fetchDegradation, fetchScorecard, fetchHealth, streamUrl } from "./api";
import Controls from "./components/Controls";
import DecisionHeader from "./components/DecisionHeader";
import GapPanel from "./components/GapPanel";
import DegradationChart from "./components/DegradationChart";
import ReasoningTrace from "./components/ReasoningTrace";
import LapHistory from "./components/LapHistory";
import Scorecard from "./components/Scorecard";

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [sessionKey, setSessionKey] = useState(null);
  const [driverNumber, setDriverNumber] = useState(null);
  const [speed, setSpeed] = useState(4);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [curves, setCurves] = useState({});
  const [scorecard, setScorecard] = useState(null);
  const [error, setError] = useState(null);
  const [llmAvailable, setLlmAvailable] = useState(false);
  const [useLlm, setUseLlm] = useState(false);
  const [selectedLap, setSelectedLap] = useState(null);

  const esRef = useRef(null);

  useEffect(() => {
    fetchHealth().then((h) => setLlmAvailable(h.llm_available)).catch(() => {});
    fetchSessions()
      .then((data) => {
        setSessions(data);
        if (data.length > 0) {
          setSessionKey(data[0].session_key);
          setDriverNumber(data[0].drivers[0]?.number);
        }
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (sessionKey == null) return;
    fetchDegradation(sessionKey).then(setCurves).catch((e) => setError(e.message));
    setScorecard(null);
    fetchScorecard(sessionKey).then(setScorecard).catch((e) => setError(e.message));
  }, [sessionKey]);

  useEffect(() => {
    return () => esRef.current?.close();
  }, []);

  function startReplay() {
    if (sessionKey == null || driverNumber == null) return;
    esRef.current?.close();
    setEvents([]);
    setSelectedLap(null);
    setError(null);

    const es = new EventSource(streamUrl(sessionKey, driverNumber, speed, useLlm));
    es.addEventListener("lap_update", (e) => {
      const data = JSON.parse(e.data);
      setEvents((prev) => [...prev, data]);
    });
    es.addEventListener("session_end", () => {
      setConnected(false);
      es.close();
    });
    es.onerror = () => {
      setError("Stream disconnected.");
      setConnected(false);
      es.close();
    };
    esRef.current = es;
    setConnected(true);
  }

  function stopReplay() {
    esRef.current?.close();
    setConnected(false);
  }

  function toggle() {
    connected ? stopReplay() : startReplay();
  }

  const currentSession = sessions.find((s) => s.session_key === sessionKey);
  const drivers = currentSession?.drivers || [];
  const latest = events[events.length - 1];
  const latestLapNumber = latest?.lap_number ?? null;
  const activeLap = selectedLap ?? latestLapNumber;
  const displayed = events.find((e) => e.lap_number === activeLap) ?? latest;
  const isLive = selectedLap === null;

  function selectLap(lapNumber) {
    setSelectedLap((prev) => (prev === lapNumber ? null : lapNumber));
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-text">
          <h1>Live Race Strategy Agent</h1>
          <p className="subtitle">
            Replays real OpenF1 telemetry lap-by-lap and reasons about pit strategy in real time.
          </p>
        </div>
        <span className={`status-pill ${connected ? "live" : ""}`}>
          <span className="status-dot" />
          {connected ? "Live" : "Idle"}
        </span>
      </header>

      <Controls
        sessions={sessions}
        sessionKey={sessionKey}
        onSessionChange={(key) => { stopReplay(); setSessionKey(key); }}
        drivers={drivers}
        driverNumber={driverNumber}
        onDriverChange={(num) => { stopReplay(); setDriverNumber(num); }}
        speed={speed}
        onSpeedChange={setSpeed}
        connected={connected}
        onToggle={toggle}
        llmAvailable={llmAvailable}
        useLlm={useLlm}
        onUseLlmChange={setUseLlm}
      />

      {error && <div className="error-banner">{error}</div>}
      {connected && useLlm && <div className="llm-active-banner">Live Claude reasoning active — pace is set by model latency, not the speed slider.</div>}

      <DecisionHeader latest={displayed} driverInfo={displayed?.driver} isLive={isLive} onBackToLive={() => setSelectedLap(null)} />

      <div className="grid-2col">
        <GapPanel latest={displayed} />
        <DegradationChart curves={curves} currentCompound={displayed?.compound} currentAge={displayed?.tire_age} />
      </div>

      <div className="grid-2col">
        <ReasoningTrace events={events} activeLap={activeLap} onSelectLap={selectLap} />
        <LapHistory events={events} activeLap={activeLap} onSelectLap={selectLap} />
      </div>

      <Scorecard scorecard={scorecard} highlightDriver={driverNumber} />

      <footer className="app-footer">
        Data: OpenF1 API (historical replay) · Not affiliated with Formula 1
      </footer>
    </div>
  );
}
