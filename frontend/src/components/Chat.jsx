import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Copy, FlaskConical, RotateCcw, Send, Wand2, X } from "lucide-react";
import { toast } from "sonner";

import { api } from "../api.js";
import { starterQuestions } from "../lib/data.js";
import IntentBadge from "./IntentBadge.jsx";
import Mascot from "./Mascot.jsx";
import ResultView from "./ResultView.jsx";

function SqlBlock({ sql, label = "SQL", onOpen }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy. Select the text and copy it instead.");
    }
  };
  return (
    <div className="sql-block">
      <div className="sql-block__bar">
        <span>{label}</span>
        <div className="sql-block__actions">
          <button className="btn btn--ghost btn--small" onClick={copy}>
            {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
            {copied ? "Copied" : "Copy"}
          </button>
          {onOpen && (
            <button className="btn btn--ghost btn--small" onClick={() => onOpen(sql)}>
              <FlaskConical size={14} aria-hidden="true" /> Test in playground
            </button>
          )}
        </div>
      </div>
      <pre>
        <code>{sql}</code>
      </pre>
    </div>
  );
}

/** "Writing and running SQL, 4s" with bouncing dots, while a step is in progress. */
function StatusLine({ text }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <p className="status-line" role="status">
      <span className="dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {text}
      {seconds > 2 ? `, ${seconds}s` : ""}
    </p>
  );
}

function BotMessage({ m, onOpen, onRetry }) {
  if (m.failed) {
    return (
      <div className="msg msg--bot">
        <Mascot mood="oops" size={40} />
        <div className="bubble bubble--error">
          <p>{m.text}</p>
          <button className="btn btn--ghost btn--small" onClick={onRetry}>
            <RotateCcw size={14} aria-hidden="true" /> Try again
          </button>
        </div>
      </div>
    );
  }

  const r = m.result || {};
  const fixed = r.original_sql && r.sql && r.original_sql.trim() !== r.sql.trim();
  const review = r.review;
  const mood = m.streaming ? "thinking" : r.error ? "oops" : "happy";

  return (
    <div className="msg msg--bot">
      <Mascot mood={mood} size={40} />
      <div className="bubble bubble--wide">
        {r.intent && <IntentBadge intent={r.intent} route={r.route} />}

        {fixed && <SqlBlock sql={r.original_sql} label="Your SQL" />}
        {r.sql && <SqlBlock sql={r.sql} label={fixed ? "Fixed SQL" : "SQL"} onOpen={onOpen} />}

        {review && review.matches === false && (
          <div className="callout callout--warn">
            <AlertTriangle size={16} aria-hidden="true" />
            <div>
              <p>
                <strong>This might not fully answer your question.</strong> {review.issue}
              </p>
              {review.suggested_sql && (
                <button className="btn btn--ghost btn--small" onClick={() => onOpen(review.suggested_sql)}>
                  <FlaskConical size={14} aria-hidden="true" /> Try the suggested SQL
                </button>
              )}
            </div>
          </div>
        )}

        {!r.error && r.columns?.length > 0 && (
          <ResultView columns={r.columns} rows={r.rows} totalRows={r.total_rows} rowLimit={r.row_limit} compact />
        )}

        {r.answer ? (
          <p className={`answer ${m.streaming ? "answer--live" : ""}`}>{r.answer}</p>
        ) : (
          m.streaming && <StatusLine key={m.status} text={m.status || "Thinking"} />
        )}
      </div>
    </div>
  );
}

export default function Chat({ sessionId, schema, messages, setMessages, onOpenInPlayground }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [rephrasing, setRephrasing] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  // Grow the text box with its content, up to a limit
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    // While the Ask tab is hidden, scrollHeight is 0; keep the CSS height instead of setting 0px
    if (el.scrollHeight > 0) el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  async function send(message) {
    const msg = message.trim();
    if (!msg || busy) return;
    setText("");
    setSuggestion(null);
    setBusy(true);

    // Add the question and an empty answer, then fill the answer in as events arrive
    const id = `${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { role: "user", text: msg },
      { role: "bot", id, streaming: true, status: "Understanding your question", result: { answer: "" } },
    ]);
    const patch = (fn) => setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
    const fail = (err) => patch(() => ({ role: "bot", id, failed: true, text: err, retry: msg }));

    try {
      await api.chatStream(sessionId, msg, (ev) => {
        if (ev.type === "status") {
          patch((m) => ({ ...m, status: ev.text }));
        } else if (ev.type === "intent") {
          patch((m) => ({ ...m, result: { ...m.result, intent: ev.intent, route: ev.route } }));
        } else if (ev.type === "sql") {
          const { type, ...data } = ev;
          patch((m) => ({ ...m, result: { ...m.result, ...data } }));
        } else if (ev.type === "token") {
          patch((m) => ({ ...m, result: { ...m.result, answer: (m.result.answer || "") + ev.text } }));
        } else if (ev.type === "done") {
          patch((m) => ({ ...m, streaming: false, result: { ...m.result, answer: m.result.answer || ev.answer } }));
        } else if (ev.type === "error") {
          fail(ev.message);
        }
      });
      patch((m) => (m.streaming ? { ...m, streaming: false } : m));
    } catch (e) {
      fail(e.message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  async function rephrase() {
    if (!text.trim()) {
      toast("Type a question first, then rephrase it.");
      return;
    }
    setRephrasing(true);
    try {
      const res = await api.rephrase(sessionId, text.trim());
      if (res.rephrased) setSuggestion({ kind: "rephrase", text: res.rephrased });
      else if (res.clarify) setSuggestion({ kind: "clarify", text: res.clarify });
      else toast(res.reason || "Couldn't find a clearer way to say that.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setRephrasing(false);
    }
  }

  const starters = starterQuestions(schema);

  return (
    <div className="chat">
      <div className="chat__scroll">
        {messages.length === 0 && (
          <div className="chat__empty">
            <Mascot mood="idle" size={80} />
            <h2>Ask your data a question</h2>
            <p className="muted">
              Ask in plain English (or Hinglish). You can also paste SQL and I'll check it for you.
            </p>
            {starters.length > 0 && (
              <div className="chips">
                {starters.map((q) => (
                  <button key={q} className="chip" onClick={() => send(q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg msg--user">
              <div className="bubble">{m.text}</div>
            </div>
          ) : (
            <BotMessage key={m.id || i} m={m} onOpen={onOpenInPlayground} onRetry={() => send(m.retry)} />
          )
        )}
        <div ref={endRef} />
      </div>

      <div className="composer">
        {suggestion && (
          <div className="suggestion">
            <Wand2 size={15} aria-hidden="true" />
            <span className="suggestion__text">
              <span className="suggestion__label">
                {suggestion.kind === "clarify" ? "To make it clearer, tell me:" : "Clearer version:"}
              </span>{" "}
              {suggestion.text}
            </span>
            {suggestion.kind === "rephrase" && (
              <button
                className="btn btn--small btn--primary"
                onClick={() => {
                  setText(suggestion.text);
                  setSuggestion(null);
                  inputRef.current?.focus();
                }}
              >
                Use this
              </button>
            )}
            <button className="icon-btn" aria-label="Dismiss suggestion" onClick={() => setSuggestion(null)}>
              <X size={14} />
            </button>
          </div>
        )}
        <div className="composer__row">
          <label htmlFor="chat-input" className="sr-only">
            Ask a question about your data
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            rows={1}
            value={text}
            placeholder="e.g. Which 5 customers spent the most?"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
          />
          <button
            className="btn btn--ghost"
            onClick={rephrase}
            disabled={busy || rephrasing}
            title="Rewrite my question more clearly"
          >
            <Wand2 size={16} aria-hidden="true" />
            <span className="hide-sm">{rephrasing ? "Rephrasing…" : "Rephrase"}</span>
          </button>
          <button className="btn btn--primary" onClick={() => send(text)} disabled={busy || !text.trim()}>
            <Send size={16} aria-hidden="true" />
            <span className="hide-sm">Send</span>
          </button>
        </div>
        <p className="composer__hint">Enter to send, Shift + Enter for a new line</p>
      </div>
    </div>
  );
}
