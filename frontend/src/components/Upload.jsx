import { useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FileSpreadsheet, GraduationCap, History, ShieldAlert, ShoppingBasket, Upload as UploadIcon, X } from "lucide-react";
import { toast } from "sonner";

import { api } from "../api.js";
import { forgetSession, getRecent } from "../lib/storage.js";
import Mascot from "./Mascot.jsx";

const ALLOWED = [".xlsx", ".xlsm", ".csv"];
const MAX_FILES = 5;
const SAMPLE_ICONS = { shop: ShoppingBasket, fraud: ShieldAlert, school: GraduationCap };

function ext(name) {
  const i = name.lastIndexOf(".");
  return i === -1 ? "" : name.slice(i).toLowerCase();
}

function timeAgo(ms) {
  const mins = Math.round((Date.now() - ms) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export default function Upload({ onReady }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState(getRecent);
  const [samples, setSamples] = useState([]);
  const [loadingSample, setLoadingSample] = useState(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  const onDrop = (dropped) => {
    const good = dropped.filter((f) => ALLOWED.includes(ext(f.name)));
    const bad = dropped.length - good.length;
    if (bad) toast.error(`${bad} file${bad > 1 ? "s were" : " was"} skipped. Use Excel (.xlsx) or CSV.`);
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      const merged = [...prev, ...good.filter((f) => !names.has(f.name))];
      if (merged.length > MAX_FILES) toast.error(`You can add up to ${MAX_FILES} files.`);
      return merged.slice(0, MAX_FILES);
    });
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, multiple: true, disabled: busy });

  async function start() {
    setBusy(true);
    try {
      const res = await api.upload(files);
      const name = files.length === 1 ? files[0].name.replace(/\.[^.]+$/, "") : `${files.length} files`;
      if (res.reused) toast.success("You've uploaded these files before, so I reopened that session.");
      onReady({ id: res.session_id, name, tableCount: res.tables.length });
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function trySample(sample) {
    setBusy(true);
    setLoadingSample(sample.id);
    try {
      const res = await api.loadSample(sample.id);
      toast(`Try asking: "${sample.try_asking}"`);
      onReady({ id: res.session_id, name: `Sample: ${sample.title}`, tableCount: res.tables.length });
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
      setLoadingSample(null);
    }
  }

  async function reopen(s) {
    try {
      await api.schema(s.id);
      onReady(s);
    } catch (e) {
      if (e.status === 404) {
        forgetSession(s.id);
        setRecent(getRecent());
        toast.error("That session no longer exists. Upload the files again.");
      } else {
        toast.error(e.message);
      }
    }
  }

  return (
    <main className="landing">
      <div className="landing__hero">
        <Mascot mood={busy ? "thinking" : files.length ? "happy" : "idle"} size={112} className="landing__mascot" />
        <h1>Drop in a spreadsheet. Ask it anything.</h1>
        <p className="landing__lede">
          TableTalk turns each sheet into a table, maps how they connect, and answers your questions with
          SQL you can see and test. Everything runs on your own computer.
        </p>
      </div>

      <section className="landing__card" aria-label="Upload files">
        <div {...getRootProps({ className: `drop ${isDragActive ? "drop--active" : ""} ${busy ? "drop--busy" : ""}` })}>
          <input {...getInputProps()} aria-label="Choose spreadsheet files" />
          <UploadIcon size={28} aria-hidden="true" />
          <p className="drop__title">{isDragActive ? "Let go to add them" : "Drag files here, or click to choose"}</p>
          <p className="drop__hint">Excel (.xlsx) or CSV. Up to {MAX_FILES} tables per upload.</p>
        </div>

        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f) => (
              <li key={f.name}>
                <FileSpreadsheet size={16} aria-hidden="true" />
                <span className="file-list__name">{f.name}</span>
                <span className="file-list__size">{(f.size / 1024).toFixed(0)} KB</span>
                <button
                  className="icon-btn"
                  aria-label={`Remove ${f.name}`}
                  disabled={busy}
                  onClick={() => setFiles(files.filter((x) => x !== f))}
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}

        <button className="btn btn--primary btn--wide" disabled={!files.length || busy} onClick={start}>
          {busy ? "Reading your files…" : "Upload and explore"}
        </button>
      </section>

      {samples.length > 0 && (
        <section className="samples" aria-label="Sample data">
          <h2>No spreadsheet handy? Try a sample</h2>
          <ul>
            {samples.map((sm) => {
              const Icon = SAMPLE_ICONS[sm.id] || FileSpreadsheet;
              return (
                <li key={sm.id} className={`sample sample--${sm.id}`}>
                  <div className="sample__icon" aria-hidden="true">
                    <Icon size={22} />
                  </div>
                  <h3>{sm.title}</h3>
                  <p className="muted">{sm.description}</p>
                  <p className="sample__ask">Try: "{sm.try_asking}"</p>
                  <button
                    className="btn btn--ghost btn--small"
                    onClick={() => trySample(sm)}
                    disabled={busy || !sm.available}
                    title={sm.available ? "" : "Run: uv run python -m scripts.make_sample_datasets"}
                  >
                    {loadingSample === sm.id ? "Loading…" : sm.available ? "Use this sample" : "Not created yet"}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {recent.length > 0 && (
        <section className="recent" aria-label="Recent uploads">
          <h2>
            <History size={16} aria-hidden="true" /> Pick up where you left off
          </h2>
          <ul>
            {recent.map((s) => (
              <li key={s.id}>
                <button className="recent__item" onClick={() => reopen(s)}>
                  <span className="recent__name">{s.name}</span>
                  <span className="recent__meta">
                    {s.tableCount} {s.tableCount === 1 ? "table" : "tables"}, {timeAgo(s.at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
