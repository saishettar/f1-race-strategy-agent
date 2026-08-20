export default function DecisionHeader({ latest, driverInfo, isLive, onBackToLive }) {
  if (!latest) {
    return (
      <div className="panel decision-header idle">
        <h3>Waiting for lap data</h3>
      </div>
    );
  }

  const isPit = latest.decision.action === "PIT";

  return (
    <div
      className={`panel decision-header ${isPit ? "pit" : "stay"}`}
      style={{ borderColor: driverInfo?.team_colour ? `#${driverInfo.team_colour}` : undefined }}
    >
      <div className="decision-header-top">
        <div>
          <div className="driver-name">{latest.driver.name} <span className="team-name">{latest.driver.team}</span></div>
          <div className="lap-label">
            Lap {latest.lap_number}
            {!isLive && <button className="btn-link" onClick={onBackToLive}>Back to live</button>}
          </div>
        </div>
        <div className={`verdict-badge ${isPit ? "pit" : "stay"}`}>
          {latest.decision.action}
        </div>
      </div>
      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Compound</span>
          <span className="stat-value">{latest.compound}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Tire Age</span>
          <span className="stat-value">{latest.tire_age} laps</span>
        </div>
        <div className="stat">
          <span className="stat-label">Lap Time</span>
          <span className="stat-value">{latest.lap_duration?.toFixed(2)}s</span>
        </div>
        <div className="stat">
          <span className="stat-label">Falloff</span>
          <span className="stat-value">{latest.decision.falloff_rate >= 0 ? "+" : ""}{latest.decision.falloff_rate.toFixed(3)}s/lap</span>
        </div>
        {latest.flag && (
          <div className="stat">
            <span className="stat-label">Track Status</span>
            <span className="stat-value flag">{latest.flag}</span>
          </div>
        )}
      </div>
    </div>
  );
}
