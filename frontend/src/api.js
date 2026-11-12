// All calls go to /api/*, which Vite forwards to the FastAPI server on port 8000.
const BASE = "/api";
const SERVER_DOWN = "Can't reach the TableTalk server. Start it with: uv run uvicorn app.main:app --reload";

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new Error(SERVER_DOWN);
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join(", ")
          : `Request failed (${res.status})`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return body;
}

function post(path, data) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/**
 * Stream a chat answer. The server sends Server-Sent Events ("data: {...}" blocks),
 * and onEvent is called for each one as soon as it arrives.
 */
async function chatStream(sessionId, message, onEvent) {
  let res;
  try {
    res = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch {
    throw new Error(SERVER_DOWN);
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new Error(msg);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

export const api = {
  chatStream,
  upload(files) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request("/upload", { method: "POST", body: form });
  },
  samples: () => request("/samples"),
  loadSample: (id) => request(`/samples/${id}`, { method: "POST" }),
  schema: (sessionId) => request(`/schema/${sessionId}`),
  chat: (sessionId, message) => post("/chat", { session_id: sessionId, message }),
  generateSql: (sessionId, question) => post("/generate-sql", { session_id: sessionId, question }),
  listTestCases: (sessionId) => request(`/test-cases/${sessionId}`),
  addTestCase: (sessionId, question, sql) => post("/test-cases", { session_id: sessionId, question, sql }),
  deleteTestCase: (id) => request(`/test-cases/${id}`, { method: "DELETE" }),
  runSql: (sessionId, sql) => post("/run-sql", { session_id: sessionId, sql }),
  // Not built on the backend yet; the UI handles the 404 gracefully.
  rephrase: (sessionId, message) => post("/rephrase", { session_id: sessionId, message }),
};
