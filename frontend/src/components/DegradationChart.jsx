const COMPOUND_COLOR = {
  SOFT: "var(--tire-soft)",
  MEDIUM: "var(--tire-medium)",
  HARD: "var(--tire-hard)",
  INTERMEDIATE: "var(--tire-inter)",
  WET: "var(--tire-wet)",
  UNKNOWN: "var(--text-muted)",
};

export default function DegradationChart({ curves, currentCompound, currentAge }) {
  const compounds = Object.keys(curves || {});
  if (compounds.length === 0) {
    return <div className="panel degradation-chart"><h3>Tire Degradation</h3><p className="empty">No data</p></div>;
  }

  const maxAge = Math.max(
    ...compounds.map((c) => curves[c].max_age_observed),
    currentAge || 0
  ) + 2;

  const allTimes = compounds.flatMap((c) => {
    const curve = curves[c];
    return [curve.intercept, curve.intercept + curve.slope * maxAge];
  });
  const minT = Math.min(...allTimes) - 0.5;
  const maxT = Math.max(...allTimes) + 0.5;

  const W = 420, H = 200, PAD = 32;
  const x = (age) => PAD + (age / maxAge) * (W - PAD * 1.5);
  const y = (t) => H - PAD - ((t - minT) / (maxT - minT)) * (H - PAD * 1.5);

  return (
    <div className="panel degradation-chart">
      <h3>Tire Degradation (fitted from race laps)</h3>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
        <line x1={PAD} y1={H - PAD} x2={W - 8} y2={H - PAD} stroke="var(--border-strong)" />
        <line x1={PAD} y1={8} x2={PAD} y2={H - PAD} stroke="var(--border-strong)" />
        <text x={PAD} y={H - 8} fill="var(--text-muted)" fontSize="10">0</text>
        <text x={W - 30} y={H - 8} fill="var(--text-muted)" fontSize="10">{maxAge} laps</text>

        {compounds.map((c) => {
          const curve = curves[c];
          const x1 = x(0), y1 = y(curve.intercept);
          const x2 = x(maxAge), y2 = y(curve.intercept + curve.slope * maxAge);
          return (
            <g key={c}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={COMPOUND_COLOR[c] || "#888"} strokeWidth="2" />
              <text x={x2 - 24} y={y2 - 6} fill={COMPOUND_COLOR[c] || "#888"} fontSize="10">{c}</text>
            </g>
          );
        })}

        {currentCompound && curves[currentCompound] && currentAge != null && (
          <circle
            cx={x(currentAge)}
            cy={y(curves[currentCompound].intercept + curves[currentCompound].slope * currentAge)}
            r="5"
            fill={COMPOUND_COLOR[currentCompound] || "var(--text)"}
            stroke="var(--bg)"
            strokeWidth="1.5"
          />
        )}
      </svg>
      <div className="legend">
        {compounds.map((c) => (
          <span key={c} className="legend-item">
            <span className="swatch" style={{ background: COMPOUND_COLOR[c] || "#888" }} />
            {c}: {curves[c].slope >= 0 ? "+" : ""}{curves[c].slope.toFixed(3)}s/lap
          </span>
        ))}
      </div>
    </div>
  );
}
