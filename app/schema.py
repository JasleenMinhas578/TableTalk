import duckdb


def profile_tables(con) -> dict:
    """Describe every table: row count, columns, types, nulls, samples, keys."""
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()]

    result = {}
    for t in tables:
        rows = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        cols = []
        for name, dtype in con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", [t]
        ).fetchall():
            nulls, distinct = con.execute(
                f'SELECT COUNT(*) - COUNT("{name}"), COUNT(DISTINCT "{name}") FROM "{t}"'
            ).fetchone()
            samples = [str(r[0]) for r in con.execute(
                f'SELECT DISTINCT "{name}" FROM "{t}" WHERE "{name}" IS NOT NULL LIMIT 3'
            ).fetchall()]
            cols.append({
                "name": name,
                "type": dtype,
                "nulls": nulls,
                "distinct": distinct,
                "samples": samples,
                # Unique and never empty = likely primary key
                "is_key": rows > 0 and nulls == 0 and distinct == rows,
            })
        result[t] = {"rows": rows, "columns": cols}
    return result


def infer_relationships(con, profile: dict, min_overlap: float = 0.9) -> list[dict]:
    """Link a column to a key column of the same name in another table."""
    rels = []
    for to_table, to_info in profile.items():
        for key in [c for c in to_info["columns"] if c["is_key"]]:
            for from_table, from_info in profile.items():
                if from_table == to_table:
                    continue
                for col in from_info["columns"]:
                    if col["name"] != key["name"] or col["is_key"]:
                        continue
                    matched = con.execute(
                        f'SELECT COUNT(DISTINCT CAST(f."{col["name"]}" AS VARCHAR)) '
                        f'FROM "{from_table}" f JOIN "{to_table}" t '
                        f'ON CAST(f."{col["name"]}" AS VARCHAR) = CAST(t."{key["name"]}" AS VARCHAR)'
                    ).fetchone()[0]
                    overlap = matched / col["distinct"] if col["distinct"] else 0
                    if overlap >= min_overlap:
                        rels.append({
                            "from_table": from_table,
                            "from_column": col["name"],
                            "to_table": to_table,
                            "to_column": key["name"],
                            "confidence": round(overlap, 2),
                        })
    return rels


def get_schema(db_path: str) -> dict:
    con = duckdb.connect(db_path, read_only=True)
    try:
        profile = profile_tables(con)
        return {"tables": profile, "relationships": infer_relationships(con, profile)}
    finally:
        con.close()


if __name__ == "__main__":
    import sys, json
    print(json.dumps(get_schema(sys.argv[1]), indent=2, default=str))