export default function LapHistory({ events, activeLap, onSelectLap }) {
  const rows = [...events].reverse();
  return (
    <div className="panel lap-history">
      <h3>Lap History</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Lap</th>
              <th>Time</th>
              <th>Compound</th>
              <th>Age</th>
              <th>Gap Ahead</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((ev) => (
              <tr
                key={ev.lap_number}
                className={[
                  ev.pit_this_lap ? "pit-row" : "",
                  ev.lap_number === activeLap ? "selected-row" : "",
                ].join(" ").trim()}
                onClick={() => onSelectLap(ev.lap_number)}
              >
                <td>{ev.lap_number}</td>
                <td>{ev.lap_duration?.toFixed(2)}s</td>
                <td>{ev.compound}</td>
                <td>{ev.tire_age}</td>
                <td>{ev.gap_ahead != null ? `${ev.gap_ahead.toFixed(1)}s` : "—"}</td>
                <td className={ev.decision.action === "PIT" ? "verdict-pit" : "verdict-stay"}>
                  {ev.decision.action}
                  {ev.pit_this_lap && <span className="actual-pit-tag"> · actual pit</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
