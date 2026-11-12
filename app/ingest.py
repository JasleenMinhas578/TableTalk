import hashlib
import os
import time
import re
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path("data/sessions")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_TABLES = 5
SESSION_DAYS = float(os.getenv("TABLETALK_SESSION_DAYS", "7"))   # 0 keeps sessions forever


def cleanup_old_sessions(days: float = SESSION_DAYS, folder: Path | None = None) -> int:
    """Delete session databases not used for `days` days. Returns how many were removed."""
    if days <= 0:
        return 0
    folder = folder or DATA_DIR
    cutoff = time.time() - days * 86400
    removed = 0
    for f in folder.glob("*.duckdb"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


class TooManyTables(ValueError):
    pass


# ---------- name helpers ----------

def clean_name(name) -> str:
    """Turn any sheet, file or column name into safe snake_case."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower()
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "_" + s
    return s


def unique_names(names) -> list[str]:
    """Clean names and add _2, _3 ... to any duplicates."""
    seen, result = {}, []
    for n in names:
        base = clean_name(n)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append(base if count == 0 else f"{base}_{count + 1}")
    return result


def content_id(paths) -> str:
    """Same files (same bytes) always give the same 32-character ID."""
    h = hashlib.sha256()
    for p in sorted(map(Path, paths), key=lambda x: x.name):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:32]


# ---------- reading ----------

def read_file(path: Path) -> dict[str, pd.DataFrame]:
    """Return {sheet_name: DataFrame} for Excel, or one entry for CSV."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(path, sheet_name=None)
    if suffix == ".csv":
        return {path.stem: pd.read_csv(path)}
    raise ValueError(f"Unsupported file type: {suffix}")


# ---------- main function ----------

def ingest_files(paths: list[str | Path], session_id: str | None = None) -> dict:
    """Load every sheet of every file into one DuckDB database for this session."""
    paths = [Path(p) for p in paths]
    session_id = session_id or content_id(paths)
    db_path = DATA_DIR / f"{session_id}.duckdb"

    # Same files uploaded before: reuse that session
    if db_path.exists():
        from app.schema import get_schema
        tables = get_schema(str(db_path))["tables"]
        return {
            "session_id": session_id,
            "db_path": str(db_path),
            "reused": True,
            "tables": [{"table": t, "rows": info["rows"],
                        "columns": [c["name"] for c in info["columns"]]}
                       for t, info in tables.items()],
        }

    # 1. Read and clean every sheet first, without touching the database
    frames = []
    for p in paths:
        sheets = read_file(p)
        for sheet_name, df in sheets.items():
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if df.empty:
                continue
            df.columns = unique_names(df.columns)
            frames.append((p, sheet_name, len(sheets), df))

    # 2. Enforce the cap before creating anything
    if not frames:
        raise ValueError("No data found in the uploaded files.")
    if len(frames) > MAX_TABLES:
        raise TooManyTables(
            f"Found {len(frames)} tables, but the limit is {MAX_TABLES}. "
            "Remove some sheets or files and try again."
        )

    # 3. Write the tables
    con = duckdb.connect(str(db_path))
    tables, used = [], set()
    try:
        for p, sheet_name, sheet_count, df in frames:
            base = clean_name(p.stem)
            if sheet_count > 1:
                base = f"{base}_{clean_name(sheet_name)}"
            name, i = base, 2
            while name in used:
                name, i = f"{base}_{i}", i + 1
            used.add(name)

            con.register("tmp_df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM tmp_df')
            con.unregister("tmp_df")

            tables.append({
                "table": name,
                "source_file": p.name,
                "sheet": str(sheet_name),
                "rows": len(df),
                "columns": list(df.columns),
            })
    except Exception:
        con.close()
        db_path.unlink(missing_ok=True)   # don't leave a half-built database behind
        raise
    con.close()

    return {"session_id": session_id, "db_path": str(db_path), "reused": False, "tables": tables}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(ingest_files(sys.argv[1:]), indent=2, default=str))