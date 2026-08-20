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

/**
 * Streams lap events from the backend. Uses fetch + a manual SSE-style parser
 * instead of EventSource, because EventSource can only do GET requests with
 * no custom headers — and the Anthropic key needs to travel as a header, not
 * a query param, so it never ends up in a URL, server access log, or browser
 * history.
 *
 * onEvent(eventType, data) is called for each "event: ...\ndata: ...\n\n"
 * block. Pass `signal` (an AbortController's signal) to allow stopping.
 */
export async function streamReplay({ sessionKey, driverNumber, speed, useLlm, apiKey }, onEvent, signal) {
  const res = await fetch(`${API_BASE}/api/replay/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-Anthropic-Api-Key": apiKey } : {}),
    },
    body: JSON.stringify({
      session_key: sessionKey,
      driver_number: driverNumber,
      speed,
      use_llm: useLlm,
    }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`stream request failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const eventMatch = block.match(/^event: (.+)$/m);
      const dataMatch = block.match(/^data: (.+)$/m);
      const eventType = eventMatch ? eventMatch[1] : "message";
      const data = dataMatch ? JSON.parse(dataMatch[1]) : null;
      onEvent(eventType, data);
    }
  }
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
