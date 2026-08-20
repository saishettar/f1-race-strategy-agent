export default function Scorecard({ scorecard, highlightDriver }) {
  if (!scorecard) {
    return <div className="panel scorecard"><h3>Agent Accuracy — This Race</h3><p className="empty">Loading</p></div>;
  }

  const { total_matched, total_actual_pit_stops, recall_pct, total_agent_pit_calls, total_extra_calls, window, per_driver } = scorecard;
  const rows = per_driver.filter((d) => d.actual_pit_laps.length || d.agent_pit_laps.length);

  return (
    <div className="panel scorecard">
      <h3>Agent Accuracy — This Race</h3>
      <div className="scorecard-headline">
        <div className="scorecard-stat">
          <span className="scorecard-big">{recall_pct != null ? `${recall_pct}%` : "—"}</span>
          <span className="stat-label">real pit stops called within {window} laps</span>
        </div>
        <div className="scorecard-sub">
          <div>{total_matched} / {total_actual_pit_stops} real stops matched</div>
          <div>{total_agent_pit_calls} total PIT calls · {total_extra_calls} didn't match a real stop</div>
        </div>
      </div>
      <div className="table-scroll scorecard-table">
        <table>
          <thead>
            <tr>
              <th>Driver</th>
              <th>Actual Pit Laps</th>
              <th>Agent PIT Laps</th>
              <th>Matched</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.driver_number} className={d.driver_number === highlightDriver ? "highlight-row" : ""}>
                <td>#{d.driver_number} {d.name}</td>
                <td>{d.actual_pit_laps.join(", ") || "—"}</td>
                <td>{d.agent_pit_laps.join(", ") || "—"}</td>
                <td>{d.matched_pit_laps.length}/{d.actual_pit_laps.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
