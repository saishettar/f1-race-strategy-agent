export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export async function fetchSessions() {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("failed to load sessions");
  return res.json();
}

export async function fetchDegradation(sessionKey) {
  const res = await fetch(`${API_BASE}/api/degradation?session_key=${sessionKey}`);
  if (!res.ok) throw new Error("failed to load degradation model");
  return res.json();
}

export function streamUrl(sessionKey, driverNumber, speed, useLlm) {
  return `${API_BASE}/api/replay/stream?session_key=${sessionKey}&driver_number=${driverNumber}&speed=${speed}&use_llm=${useLlm}`;
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("failed to load health");
  return res.json();
}

export async function fetchScorecard(sessionKey) {
  const res = await fetch(`${API_BASE}/api/scorecard?session_key=${sessionKey}`);
  if (!res.ok) throw new Error("failed to load scorecard");
  return res.json();
}
