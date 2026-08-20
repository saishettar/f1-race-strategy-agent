export default function Controls({
  sessions, sessionKey, onSessionChange,
  drivers, driverNumber, onDriverChange,
  speed, onSpeedChange,
  connected, onToggle,
  llmAvailable, useLlm, onUseLlmChange,
}) {
  return (
    <div className="panel controls">
      <div className="control-group">
        <label>Session</label>
        <select value={sessionKey ?? ""} onChange={(e) => onSessionChange(Number(e.target.value))}>
          {sessions.map((s) => (
            <option key={s.session_key} value={s.session_key}>
              {s.year} {s.country} — {s.circuit}
            </option>
          ))}
        </select>
      </div>
      <div className="control-group">
        <label>Car</label>
        <select value={driverNumber ?? ""} onChange={(e) => onDriverChange(Number(e.target.value))}>
          {drivers.map((d) => (
            <option key={d.number} value={d.number}>
              #{d.number} {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className="control-group">
        <label>Replay Speed: {speed}x</label>
        <input
          type="range" min="1" max="20" step="1"
          value={speed}
          onChange={(e) => onSpeedChange(Number(e.target.value))}
        />
      </div>
      <label className={`llm-toggle ${!llmAvailable ? "disabled" : ""}`} title={llmAvailable ? "Route each pit decision through a real Claude tool-use agent instead of the rule-based one" : "Set ANTHROPIC_API_KEY in backend/.env to enable"}>
        <input
          type="checkbox"
          checked={useLlm}
          disabled={!llmAvailable || connected}
          onChange={(e) => onUseLlmChange(e.target.checked)}
        />
        Claude reasoning{!llmAvailable ? " (no API key)" : ""}
      </label>

      <button className={`btn toggle-btn ${connected ? "btn-secondary" : "btn-primary"}`} onClick={onToggle}>
        {connected ? "Stop Replay" : "Start Replay"}
      </button>
    </div>
  );
}
