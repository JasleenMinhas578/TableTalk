"""Decide whether the AI's query result matches the correct result.

Two SQL queries can be written very differently and still give the same answer,
so we never compare the SQL text. We run both and compare what comes back.

The rules:
  1. Both results must have the same number of rows.
  2. Every column in the correct result must also appear in the AI's result,
     with the same values. Column names don't matter ("n" vs "order_count").
  3. Extra columns in the AI's result are fine (e.g. it also returned the name).
  4. Row order doesn't matter (with LIMIT, *which* rows come back still has to match).
     Ties make strict order unreliable, so sorting itself is not checked.
  5. Numbers are rounded to 2 decimals, so 2.0 equals 2 and 3.3333 equals 3.33.
"""

from datetime import date, datetime
from decimal import Decimal


def norm(value):
    """Make values comparable: round numbers, turn dates into text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _sort_key(v):
    return (v is None, str(type(v)), v if v is not None else 0)


def columns_of(rows: list, ordered: bool) -> list[list]:
    """Turn rows into a list of columns. Unordered columns are sorted so order can't matter."""
    if not rows:
        return []
    cols = [[norm(r[i]) for r in rows] for i in range(len(rows[0]))]
    return cols if ordered else [sorted(c, key=_sort_key) for c in cols]


def results_match(expected_rows: list, actual_rows: list, ordered: bool = False) -> tuple[bool, str]:
    """Return (match, reason)."""
    if len(expected_rows) != len(actual_rows):
        return False, f"expected {len(expected_rows)} rows, got {len(actual_rows)}"
    if not expected_rows:
        return True, "both empty"

    expected_cols = columns_of(expected_rows, ordered)
    remaining = columns_of(actual_rows, ordered)
    for i, col in enumerate(expected_cols):
        if col in remaining:
            remaining.remove(col)          # each AI column can match only one expected column
        else:
            return False, f"column {i + 1} of the correct answer is missing or has different values"
    return True, "same values"
