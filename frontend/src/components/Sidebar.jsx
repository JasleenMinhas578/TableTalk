import { useState } from "react";
import { ChevronRight, Eye, KeyRound, Link2 } from "lucide-react";

import { foreignKeys, friendlyType } from "../lib/data.js";

export default function Sidebar({ schema, onPreview }) {
  const tables = Object.entries(schema?.tables || {});
  const fks = foreignKeys(schema);
  // null = nothing touched yet, so the first table starts open
  const [touched, setTouched] = useState(null);
  const open = touched ?? new Set(tables.slice(0, 1).map(([t]) => t));

  const toggle = (t) => {
    const next = new Set(open);
    next.has(t) ? next.delete(t) : next.add(t);
    setTouched(next);
  };

  if (!schema) return <aside className="sidebar"><p className="muted">Loading tables…</p></aside>;

  return (
    <aside className="sidebar" aria-label="Your tables">
      <h2 className="sidebar__title">Your tables</h2>
      <ul className="tables">
        {tables.map(([t, info]) => {
          const isOpen = open.has(t);
          return (
            <li key={t} className={`table-item ${isOpen ? "table-item--open" : ""}`}>
              <div className="table-item__head">
                <button className="table-item__toggle" aria-expanded={isOpen} onClick={() => toggle(t)}>
                  <ChevronRight size={16} className="chev" aria-hidden="true" />
                  <span className="table-item__name">{t}</span>
                  <span className="table-item__rows">{info.rows.toLocaleString()} rows</span>
                </button>
                <button className="icon-btn" title={`Preview ${t} in the playground`} aria-label={`Preview ${t}`} onClick={() => onPreview(t)}>
                  <Eye size={15} />
                </button>
              </div>
              {isOpen && (
                <ul className="columns">
                  {info.columns.map((c) => {
                    const isFk = fks.has(`${t}.${c.name}`);
                    return (
                      <li key={c.name} title={c.samples?.length ? `e.g. ${c.samples.join(", ")}` : ""}>
                        <span className="col-icon" aria-hidden="true">
                          {c.is_key ? <KeyRound size={13} className="ico-key" /> : isFk ? <Link2 size={13} className="ico-link" /> : null}
                        </span>
                        <span className="col-name">{c.name}</span>
                        <span className="col-type">{friendlyType(c.type)}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      <p className="legend">
        <KeyRound size={13} className="ico-key" aria-hidden="true" /> unique key
        <Link2 size={13} className="ico-link" aria-hidden="true" /> links to another table
      </p>
    </aside>
  );
}
