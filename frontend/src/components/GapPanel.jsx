function fmt(v) {
  return v == null ? "—" : `${v.toFixed(1)}s`;
}

export default function GapPanel({ latest }) {
  return (
    <div className="panel gap-panel">
      <h3>Gaps</h3>
      <div className="gap-row">
        <div className="gap-tile">
          <span className="stat-label">Car Behind</span>
          <span className="stat-value">{fmt(latest?.gap_behind)}</span>
        </div>
        <div className="gap-tile highlight">
          <span className="stat-label">YOUR CAR</span>
          <span className="stat-value">#{latest?.driver?.number ?? "—"}</span>
        </div>
        <div className="gap-tile">
          <span className="stat-label">Car Ahead</span>
          <span className="stat-value">{fmt(latest?.gap_ahead)}</span>
          {latest?.rival_ahead?.compound && (
            <span className="rival-tag">
              #{latest.rival_ahead.driver_number} · {latest.rival_ahead.compound} ({latest.rival_ahead.tire_age}L)
            </span>
          )}
        </div>
      </div>
      <div className="gap-leader">
        <span className="stat-label">Gap to Leader</span>
        <span className="stat-value">{fmt(latest?.gap_to_leader)}</span>
      </div>
      {latest?.weather && (
        <div className="gap-leader weather-row">
          <span className="stat-label">Conditions</span>
          <span className={`stat-value ${latest.weather.rainfall ? "flag" : ""}`}>
            {latest.weather.track_temp != null ? `Track ${latest.weather.track_temp.toFixed(0)}°C` : "—"}
            {latest.weather.rainfall ? " · RAIN" : ""}
          </span>
        </div>
      )}
    </div>
  );
}
