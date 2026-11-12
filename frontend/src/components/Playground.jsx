import { useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { sql as sqlLang } from "@codemirror/lang-sql";
import { AlertCircle, ClipboardCheck, Play, Sparkles, Trash2, Wrench } from "lucide-react";
import { toast } from "sonner";

import { api } from "../api.js";
import { editorSchema, starterQuestions } from "../lib/data.js";
import ResultView from "./ResultView.jsx";

export default function Playground({ sessionId, schema, sql, setSql }) {
  const [request, setRequest] = useState(""); // plain-English description for the AI
  const [writing, setWriting] = useState(false);
  const [running, setRunning] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [result, setResult] = useState(null); // { columns, rows, total_rows, row_limit, sql }
  const [error, setError] = useState(null);
  const [fix, setFix] = useState(null); // { sql, note }
  const [history, setHistory] = useState([]);
  const [cases, setCases] = useState([]); // the SQL test set for this dataset
  const [caseQuestion, setCaseQuestion] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.listTestCases(sessionId).then(setCases).catch(() => setCases([]));
  }, [sessionId]);

  const extensions = useMemo(
    () => [sqlLang({ schema: editorSchema(schema), upperCaseKeywords: true })],
    [schema]
  );
  const ideas = starterQuestions(schema).filter((q) => q !== "What tables do I have?");

  async function run(code = sql) {
    if (!code.trim() || running) return;
    setRunning(true);
    setError(null);
    setFix(null);
    setSaved(false);
    setCaseQuestion(request);
    const started = performance.now();
    try {
      const res = await api.runSql(sessionId, code);
      const ms = Math.round(performance.now() - started);
      setResult({ ...res, sql: code });
      setHistory((h) => [{ sql: code, rows: res.total_rows, ms, at: Date.now() }, ...h.filter((x) => x.sql !== code)].slice(0, 8));
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  // Describe it in English, AI writes the SQL into the editor and runs it
  async function writeForMe(text = request) {
    const q = text.trim();
    if (!q || writing) return;
    setRequest(q);
    setWriting(true);
    setError(null);
    setFix(null);
    try {
      const res = await api.generateSql(sessionId, q);
      if (!res.sql) {
        setError(res.error || "The AI couldn't write a query for that. Try rewording it.");
        return;
      }
      setSql(res.sql);
      if (res.error) {
        setResult(null);
        setError(`The AI's query still has a problem: ${res.error}. Edit it below, or press "Fix my SQL".`);
      } else {
        await run(res.sql);
        if (res.review?.matches === false && res.review.issue) {
          toast.warning(`This might not fully answer your request: ${res.review.issue}`);
        }
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setWriting(false);
    }
  }

  // Send the editor's SQL to the agent's fix mode (with the description, if any, to check against)
  async function fixMine() {
    if (!sql.trim()) return;
    setFixing(true);
    try {
      const message = request.trim() ? `${sql.trim()}\n${request.trim()}` : sql.trim();
      const res = await api.chat(sessionId, message);
      if (res.intent !== "sql" || !res.sql) {
        toast("That doesn't look like SQL. Check that it starts with SELECT.");
      } else if (res.sql.trim() === sql.trim() && res.review?.matches !== false) {
        toast.success("Your SQL looks good. Nothing to fix.");
      } else {
        const note = res.error
          ? `I couldn't fully fix it: ${res.error}`
          : res.review?.matches === false
            ? res.review.issue
            : "This version runs without errors.";
        setFix({ sql: res.review?.suggested_sql || res.sql, note });
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setFixing(false);
    }
  }

  async function saveCase() {
    if (!result || !caseQuestion.trim()) return;
    try {
      const c = await api.addTestCase(sessionId, caseQuestion.trim(), result.sql);
      setCases((prev) => [...prev, c]);
      setSaved(true);
      toast.success("Added to your SQL test set.");
    } catch (e) {
      toast.error(e.message);
    }
  }

  async function removeCase(id) {
    try {
      await api.deleteTestCase(id);
      setCases((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      toast.error(e.message);
    }
  }

  return (
    <div className="playground">
      <section className="pg-editor" aria-label="SQL playground">
        <div className="pg-editor__head">
          <h2>SQL playground</h2>
          <p className="muted">Write SQL yourself, or describe what you want and let AI write it for you.</p>
        </div>

        <form
          className="ai-box"
          onSubmit={(e) => {
            e.preventDefault();
            writeForMe();
          }}
        >
          <label htmlFor="ai-request" className="ai-box__label">
            <Sparkles size={16} aria-hidden="true" /> Ask AI to write the query
          </label>
          <div className="ai-box__row">
            <input
              id="ai-request"
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder="e.g. Which 5 customers spent the most?"
              disabled={writing}
            />
            <button className="btn btn--primary" type="submit" disabled={writing || !request.trim()}>
              <Sparkles size={16} aria-hidden="true" /> {writing ? "Writing…" : "Write SQL for me"}
            </button>
          </div>
          {ideas.length > 0 && !request && (
            <div className="ai-box__ideas">
              {ideas.map((q) => (
                <button key={q} type="button" className="chip chip--small" onClick={() => writeForMe(q)}>
                  {q}
                </button>
              ))}
            </div>
          )}
        </form>

        <div className="editor-label">
          <span>SQL</span>
          {sql.trim() && (
            <button className="btn btn--ghost btn--small" onClick={() => setSql("")}>
              Clear
            </button>
          )}
        </div>
        <div
          className="editor"
          onKeyDownCapture={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              e.stopPropagation();
              run();
            }
          }}
        >
          <CodeMirror
            value={sql}
            height="170px"
            extensions={extensions}
            onChange={setSql}
            placeholder="SELECT * FROM your_table LIMIT 10"
            basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true }}
          />
        </div>

        <div className="pg-actions">
          <button className="btn btn--primary" onClick={() => run()} disabled={running || !sql.trim()}>
            <Play size={16} aria-hidden="true" /> {running ? "Running…" : "Run query"}
          </button>
          <button className="btn btn--ghost" onClick={fixMine} disabled={fixing || !sql.trim()}>
            <Wrench size={16} aria-hidden="true" /> {fixing ? "Checking…" : "Fix my SQL"}
          </button>
          <span className="kbd-hint">
            <kbd>⌘</kbd> + <kbd>Enter</kbd> runs it
          </span>
        </div>

        {fix && (
          <div className="callout callout--fix">
            <Wrench size={16} aria-hidden="true" />
            <div>
              <p>{fix.note}</p>
              <pre>
                <code>{fix.sql}</code>
              </pre>
              <div className="pg-actions">
                <button
                  className="btn btn--primary btn--small"
                  onClick={() => {
                    setSql(fix.sql);
                    setFix(null);
                    run(fix.sql);
                  }}
                >
                  Use this and run
                </button>
                <button className="btn btn--ghost btn--small" onClick={() => setFix(null)}>
                  Keep mine
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="callout callout--error" role="alert">
            <AlertCircle size={16} aria-hidden="true" />
            <div>
              <p>{error}</p>
              <p className="muted">Press "Fix my SQL" to get a corrected version.</p>
            </div>
          </div>
        )}

        {result && (
          <>
            <ResultView
              columns={result.columns}
              rows={result.rows}
              totalRows={result.total_rows}
              rowLimit={result.row_limit}
            />
            <div className="add-case">
              <div className="add-case__head">
                <ClipboardCheck size={16} aria-hidden="true" />
                <strong>Add to your SQL test set</strong>
              </div>
              {saved ? (
                <p className="muted small">Saved. The eval will check that the AI can answer this question correctly.</p>
              ) : (
                <>
                  <p className="muted small">
                    Only add it if you've checked this result is right. The eval script asks the AI the same question
                    and compares its answer with this one.
                  </p>
                  <div className="add-case__row">
                    <label htmlFor="case-question" className="sr-only">Question this SQL answers</label>
                    <input
                      id="case-question"
                      value={caseQuestion}
                      onChange={(e) => setCaseQuestion(e.target.value)}
                      placeholder="What question does this SQL answer?"
                    />
                    <button className="btn btn--small btn--good" onClick={saveCase} disabled={!caseQuestion.trim()}>
                      Save as a test case
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </section>

      <aside className="pg-side" aria-label="History and saved checks">
        <h3>Recent runs</h3>
        {history.length === 0 ? (
          <p className="muted small">Queries you run show up here. Click one to load it again.</p>
        ) : (
          <ul className="history">
            {history.map((h) => (
              <li key={h.at}>
                <button onClick={() => setSql(h.sql)} title={h.sql}>
                  <code>{h.sql}</code>
                  <span className="muted small">
                    {h.rows.toLocaleString()} rows, {h.ms} ms
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <h3 className="pg-side__title">Your SQL test set ({cases.length})</h3>
        <p className="muted small">
          Questions with SQL you've checked is right. Run <code>uv run python -m evals.run_sql_eval</code> to see how
          often the AI gets them right. Saved in <code>evals/sql_cases.jsonl</code>.
        </p>
        {cases.length > 0 && (
          <ul className="checks">
            {cases.map((c) => (
              <li key={c.id}>
                <span title={c.sql}>{c.question}</span>
                <button className="icon-btn" aria-label={`Remove "${c.question}"`} title="Remove" onClick={() => removeCase(c.id)}>
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
