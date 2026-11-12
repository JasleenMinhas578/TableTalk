// Small, safe wrappers around localStorage. Storage can be blocked or empty,
// so every read and write is guarded and the app works without it.

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

// ---------- recent uploads ----------

const RECENT = "tabletalk.recent";

export function getRecent() {
  return read(RECENT, []);
}

export function rememberSession(session) {
  const list = getRecent().filter((s) => s.id !== session.id);
  list.unshift({ id: session.id, name: session.name, tableCount: session.tableCount, at: Date.now() });
  write(RECENT, list.slice(0, 6));
}

export function forgetSession(id) {
  write(RECENT, getRecent().filter((s) => s.id !== id));
}

// ---------- saved checks from the playground ----------

const checksKey = (id) => `tabletalk.checks.${id}`;

export function getChecks(sessionId) {
  return read(checksKey(sessionId), []);
}

export function saveChecks(sessionId, checks) {
  write(checksKey(sessionId), checks);
}
