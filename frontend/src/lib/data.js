// Helpers for showing query results and schema info.

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function formatCell(value) {
  if (value === null || value === undefined) return null;
  if (isNum(value)) {
    return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export function toCsv(columns, rows) {
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
}

export function downloadText(filename, text, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Friendly name for a DuckDB type. */
export function friendlyType(type = "") {
  const t = type.toUpperCase();
  if (/INT|HUGEINT/.test(t)) return "whole number";
  if (/DOUBLE|FLOAT|DECIMAL|REAL|NUMERIC/.test(t)) return "number";
  if (/TIMESTAMP/.test(t)) return "date & time";
  if (/DATE/.test(t)) return "date";
  if (/BOOL/.test(t)) return "yes / no";
  return "text";
}

/** Short label for a table: "shop_data_customers" -> "customers". */
export function shortName(table) {
  const parts = table.split("_");
  return parts[parts.length - 1] || table;
}

/** Set of "table.column" that point to another table. */
export function foreignKeys(schema) {
  return new Set((schema?.relationships || []).map((r) => `${r.from_table}.${r.from_column}`));
}

/** Starter questions built from the user's own tables. */
export function starterQuestions(schema) {
  const tables = Object.keys(schema?.tables || {});
  if (!tables.length) return [];
  const qs = ["What tables do I have?"];
  const rel = schema.relationships?.[0];
  if (rel) qs.push(`Top 5 ${shortName(rel.to_table)} by number of ${shortName(rel.from_table)}`);
  qs.push(`How many rows are in ${shortName(tables[0])}?`);
  const withDate = tables.find((t) => schema.tables[t].columns.some((c) => /DATE/i.test(c.type)));
  if (withDate) qs.push(`How many ${shortName(withDate)} per month?`);
  return qs.slice(0, 4);
}

/** Autocomplete schema for the SQL editor: { table: [columns] }. */
export function editorSchema(schema) {
  const out = {};
  Object.entries(schema?.tables || {}).forEach(([t, info]) => {
    out[t] = info.columns.map((c) => c.name);
  });
  return out;
}
