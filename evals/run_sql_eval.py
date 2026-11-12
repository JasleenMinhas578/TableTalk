"""Score the text-to-SQL agent on the SQL test set.

Run from the TableTalk folder (Ollama must be running):
    uv run python -m evals.run_sql_eval                  # every case
    uv run python -m evals.run_sql_eval --dataset fraud  # one dataset
    uv run python -m evals.run_sql_eval --limit 5        # a quick check

For each test case (a question + SQL a person checked is correct):
  1. Open the right database (samples are loaded by name, uploads by session id).
  2. Run the correct SQL to get the expected answer.
  3. Ask the agent the question, exactly as the website would, and time it.
  4. Run the agent's SQL and compare the two results (see evals/compare.py).
  5. Record the outcome: correct, wrong result, or no working SQL.

At the end it prints the scores and saves a full report to evals/results/.
"""

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import duckdb

from app.agent.sql_agent import SQL_MODEL, ask
from app.eval_cases import CASES_FILE, read_cases
from app.ingest import DATA_DIR, ingest_files
from app.samples import SAMPLES, sample_path
from evals.compare import results_match

SEED_FILE = Path("evals/seed_cases.jsonl")
RESULTS_DIR = Path("evals/results")


def db_for(dataset: str) -> str | None:
    """Find (or load) the DuckDB file for a dataset name."""
    if dataset in SAMPLES:
        path = sample_path(dataset)
        return ingest_files([path])["db_path"] if path.exists() else None
    if dataset.startswith("session:"):
        path = DATA_DIR / f"{dataset.split(':', 1)[1]}.duckdb"
        return str(path) if path.exists() else None
    return None


def run_query(db_path: str, sql: str) -> list:
    """Run SQL read-only and return every row (no row cap, so the comparison is complete)."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def evaluate_case(case: dict) -> dict:
    out = {"id": case["id"], "dataset": case["dataset"], "question": case["question"],
           "expected_sql": case["sql"]}

    db_path = db_for(case["dataset"])
    if not db_path:
        return {**out, "outcome": "skipped", "reason": "dataset not found on this machine"}

    # Step 2: the expected answer
    try:
        expected = run_query(db_path, case["sql"])
    except Exception as e:
        return {**out, "outcome": "bad_test_case", "reason": f"the saved SQL fails: {e}"}

    # Step 3: ask the agent, the same way the website does
    start = time.perf_counter()
    result = ask(db_path, case["question"])
    seconds = round(time.perf_counter() - start, 2)
    out.update({"ai_sql": result.get("sql"), "seconds": seconds, "retries": result.get("retries", 0)})

    if result.get("error") or not result.get("sql"):
        return {**out, "outcome": "no_working_sql", "reason": result.get("error") or "no SQL produced"}

    # Step 4: run the agent's SQL and compare
    try:
        actual = run_query(db_path, result["sql"])
    except Exception as e:
        return {**out, "outcome": "no_working_sql", "reason": str(e)}

    match, reason = results_match(expected, actual)
    return {**out, "outcome": "correct" if match else "wrong_result", "reason": reason}


def summarise(results: list[dict]) -> dict:
    scored = [r for r in results if r["outcome"] in ("correct", "wrong_result", "no_working_sql")]
    n = len(scored)
    if not n:
        return {"cases_scored": 0}

    correct = sum(r["outcome"] == "correct" for r in scored)
    working = sum(r["outcome"] != "no_working_sql" for r in scored)
    first_try = sum(r["outcome"] != "no_working_sql" and r.get("retries", 0) == 0 for r in scored)
    needed_retry = [r for r in scored if r.get("retries", 0) > 0]
    repaired = sum(r["outcome"] != "no_working_sql" for r in needed_retry)
    times = sorted(r["seconds"] for r in scored)

    return {
        "cases_scored": n,
        "execution_accuracy": round(correct / n, 3),
        "valid_sql_rate": round(working / n, 3),
        "first_try_rate": round(first_try / n, 3),
        "self_repair_rate": round(repaired / len(needed_retry), 3) if needed_retry else None,
        "median_seconds": statistics.median(times),
        "p95_seconds": times[min(len(times) - 1, int(0.95 * len(times)))],
        "skipped": sum(r["outcome"] == "skipped" for r in results),
        "bad_test_cases": sum(r["outcome"] == "bad_test_case" for r in results),
    }


def pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def main():
    parser = argparse.ArgumentParser(description="Score the text-to-SQL agent.")
    parser.add_argument("--dataset", help="only run one dataset, e.g. shop, fraud or school")
    parser.add_argument("--limit", type=int, help="only run the first N cases")
    parser.add_argument("--no-seed", action="store_true", help="skip the built-in seed cases")
    args = parser.parse_args()

    cases = ([] if args.no_seed else read_cases(SEED_FILE)) + read_cases(CASES_FILE)
    if args.dataset:
        cases = [c for c in cases if c["dataset"] == args.dataset]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No test cases found. Save some from the playground, or check evals/seed_cases.jsonl.")

    print(f"Running {len(cases)} test cases with {SQL_MODEL}. Each one asks the local model, so this takes a while.\n")
    results = []
    for i, case in enumerate(cases, 1):
        r = evaluate_case(case)
        results.append(r)
        mark = {"correct": "PASS", "wrong_result": "FAIL", "no_working_sql": "FAIL"}.get(r["outcome"], "SKIP")
        took = f"{r['seconds']}s" if "seconds" in r else ""
        print(f"[{i:>3}/{len(cases)}] {mark}  {took:>7}  ({r['dataset']}) {r['question']}")
        if mark == "FAIL":
            print(f"               {r['outcome']}: {r['reason']}")

    summary = summarise(results)
    by_dataset = {
        d: summarise([r for r in results if r["dataset"] == d])
        for d in sorted({r["dataset"] for r in results})
    }

    print(f"\n========== SQL eval ({SQL_MODEL}) ==========")
    if summary["cases_scored"]:
        print(f"Execution accuracy : {pct(summary['execution_accuracy'])}  (right answer)")
        print(f"Valid SQL rate     : {pct(summary['valid_sql_rate'])}  (query ran)")
        print(f"First-try rate     : {pct(summary['first_try_rate'])}  (ran without any retry)")
        print(f"Self-repair rate   : {pct(summary['self_repair_rate'])}  (fixed after an error)")
        print(f"Time per question  : median {summary['median_seconds']}s, p95 {summary['p95_seconds']}s")
        print("\nBy dataset:")
        for d, s in by_dataset.items():
            if s["cases_scored"]:
                print(f"  {d:<20} {pct(s['execution_accuracy']):>5} of {s['cases_scored']}")
    if summary.get("skipped") or summary.get("bad_test_cases"):
        print(f"\nSkipped: {summary.get('skipped', 0)}, bad test cases: {summary.get('bad_test_cases', 0)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report = RESULTS_DIR / f"sql_eval_{SQL_MODEL.replace(':', '-')}_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(json.dumps({"sql_model": SQL_MODEL, "summary": summary, "by_dataset": by_dataset, "results": results},
                                 indent=2, default=str))
    print(f"\nFull report: {report}")


if __name__ == "__main__":
    main()
