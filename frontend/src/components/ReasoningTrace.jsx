import { useEffect, useRef } from "react";

export default function ReasoningTrace({ events, activeLap, onSelectLap }) {
  const scrollRef = useRef(null);
  const rowRefs = useRef({});
  const ordered = [...events].reverse();

  useEffect(() => {
    const node = rowRefs.current[activeLap];
    node?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeLap]);

  return (
    <div className="panel reasoning-trace">
      <h3>Agent Reasoning — All Laps</h3>
      <div className="trace-scroll" ref={scrollRef}>
        {ordered.length === 0 && <p className="empty">No laps yet.</p>}
        {ordered.map((ev) => {
          const isActive = ev.lap_number === activeLap;
          return (
            <div
              key={ev.lap_number}
              ref={(el) => { rowRefs.current[ev.lap_number] = el; }}
              className={`trace-lap ${isActive ? "active" : ""}`}
              onClick={() => onSelectLap(ev.lap_number)}
            >
              <div className="trace-lap-head">
                <span className="trace-lap-number">Lap {ev.lap_number}</span>
                <span className={`pill ${ev.decision.action === "PIT" ? "pill-danger" : "pill-success"}`}>
                  {ev.decision.action}
                </span>
              </div>
              {isActive && (
                <ol className="trace-steps">
                  {ev.decision.reasoning.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
