export default function Controls({
  sessions, sessionKey, onSessionChange,
  drivers, driverNumber, onDriverChange,
  speed, onSpeedChange,
  connected, onToggle,
  useLlm, onUseLlmChange,
  apiKey, onApiKeyChange,
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

      <div className="control-group llm-control-group">
        <label className="llm-toggle">
          <input
            type="checkbox"
            checked={useLlm}
            disabled={connected}
            onChange={(e) => onUseLlmChange(e.target.checked)}
          />
          Claude reasoning
        </label>
        {useLlm && (
          <input
            type="password"
            className="api-key-input"
            placeholder="sk-ant-..."
            value={apiKey}
            disabled={connected}
            onChange={(e) => onApiKeyChange(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        )}
      </div>

      <button className={`btn toggle-btn ${connected ? "btn-secondary" : "btn-primary"}`} onClick={onToggle}>
        {connected ? "Stop Replay" : "Start Replay"}
      </button>

      {useLlm && (
        <p className="api-key-note">
          Stored only in your browser (localStorage), sent directly to this app's backend per request. Never
          logged or persisted server-side. Get a key at{" "}
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">console.anthropic.com</a>.
        </p>
      )}
    </div>
  );
}
