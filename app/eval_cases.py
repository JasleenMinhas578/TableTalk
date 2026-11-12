"""The SQL test set: questions paired with SQL a person checked is correct.

Cases saved from the playground go to evals/sql_cases.jsonl (one JSON object per line).
The eval script (evals/run_sql_eval.py) reads them to score the AI.

Each case remembers which dataset it belongs to:
  - a sample id ("shop", "fraud", "school") if the session is a sample, so it works on any machine
  - "session:<id>" for the user's own uploads
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.ingest import content_id
from app.samples import SAMPLES, sample_path

CASES_FILE = Path("evals/sql_cases.jsonl")
_lock = threading.Lock()


def dataset_for_session(session_id: str) -> str:
    """Name the dataset behind a session: a sample id, or session:<id>."""
    for sample_id in SAMPLES:
        path = sample_path(sample_id)
        if path.exists() and content_id([path]) == session_id:
            return sample_id
    return f"session:{session_id}"


def read_cases(path: Path = CASES_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def list_cases(session_id: str) -> list[dict]:
    dataset = dataset_for_session(session_id)
    return [c for c in read_cases() if c["dataset"] == dataset]


def add_case(session_id: str, question: str, sql: str) -> dict:
    case = {
        "id": uuid.uuid4().hex[:12],
        "dataset": dataset_for_session(session_id),
        "question": question.strip(),
        "sql": sql.strip().rstrip(";"),
        "source": "playground",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _lock:
        CASES_FILE.parent.mkdir(exist_ok=True)
        with CASES_FILE.open("a") as f:
            f.write(json.dumps(case) + "\n")
    return case


def delete_case(case_id: str) -> bool:
    with _lock:
        cases = read_cases()
        kept = [c for c in cases if c["id"] != case_id]
        if len(kept) == len(cases):
            return False
        CASES_FILE.write_text("".join(json.dumps(c) + "\n" for c in kept))
    return True
