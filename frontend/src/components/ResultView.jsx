import { Download, Info } from "lucide-react";

import { downloadText, formatCell, toCsv } from "../lib/data.js";

export default function ResultView({ columns = [], rows = [], totalRows, rowLimit, compact = false }) {
  if (!columns.length) return null;

  const total = totalRows ?? rows.length;
  const capped = total > rows.length;

  return (
    <div className={`result ${compact ? "result--compact" : ""}`}>
      <div className="result__bar">
        <span className="result__count">
          {total.toLocaleString()} {total === 1 ? "row" : "rows"}
          {capped && `, showing the first ${rows.length.toLocaleString()}`}
        </span>
        <button
          className="btn btn--ghost btn--small"
          onClick={() => downloadText("tabletalk-result.csv", toCsv(columns, rows))}
          title={capped ? `Downloads the ${rows.length} rows shown` : "Download these rows"}
        >
          <Download size={14} aria-hidden="true" /> CSV
        </button>
      </div>

      {capped && (
        <p className="result__cap" role="note">
          <Info size={14} aria-hidden="true" />
          This query returned {total.toLocaleString()} rows. TableTalk shows at most{" "}
          {(rowLimit ?? rows.length).toLocaleString()} here. Add a filter, GROUP BY or LIMIT to see the rows you need.
        </p>
      )}

      {rows.length === 0 ? (
        <p className="result__empty">The query ran but returned no rows.</p>
      ) : (
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col" className="grid__rownum" aria-label="Row number">#</th>
                {columns.map((c, i) => (
                  <th key={`${c}-${i}`} scope="col">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  <td className="grid__rownum">{ri + 1}</td>
                  {r.map((v, ci) => {
                    const shown = formatCell(v);
                    return (
                      <td key={ci} className={typeof v === "number" ? "num" : ""}>
                        {shown === null ? <span className="null">empty</span> : shown}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
