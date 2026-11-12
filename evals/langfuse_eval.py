"""Run the SQL eval as a Langfuse experiment, so every run shows up in the dashboard.

Run from the TableTalk folder (Ollama and Langfuse must be running):
    uv run python -m evals.langfuse_eval
    uv run python -m evals.langfuse_eval --run-name qwen-14b-try1

What happens:
  1. Upload: every test case (seed + saved from the playground) becomes an item in the
     Langfuse dataset "tabletalk-sql". Input = question + dataset, expected output = correct SQL.
     Re-running updates items instead of duplicating them (each has a fixed id).
  2. Experiment: Langfuse runs our task on each item. The task is the same evaluate_case()
     the local eval uses, so both always score the same way.
  3. Scores: two evaluators turn each result into scores Langfuse stores on the trace:
     execution_accuracy (1 = right answer) and valid_sql (1 = the SQL ran).
  4. Compare: in Langfuse, open Datasets > tabletalk-sql > Runs to see runs side by side,
     and click any item to see the agent's full trace (SQL, retries, review).
"""

import argparse
from datetime import datetime

from dotenv import load_dotenv
from langfuse import Evaluation, get_client

from app.agent.sql_agent import SQL_MODEL
from app.eval_cases import CASES_FILE, read_cases
from evals.run_sql_eval import SEED_FILE, evaluate_case

load_dotenv()

DATASET = "tabletalk-sql"


def upload_cases(langfuse, cases: list[dict]) -> None:
    try:
        langfuse.create_dataset(name=DATASET, description="TableTalk text-to-SQL test cases")
    except Exception:
        pass  # already exists
    for c in cases:
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"tabletalk-{c['id']}",                       # fixed id, so re-uploading updates it
            input={"question": c["question"], "dataset": c["dataset"]},
            expected_output={"sql": c["sql"]},
            metadata={"source": c.get("source", "playground")},
        )
    print(f"Uploaded {len(cases)} test cases to the Langfuse dataset '{DATASET}'.")


def task(*, item, **kwargs):
    """Run one test case through the agent (same code as the local eval)."""
    case = {
        "id": item.id,
        "dataset": item.input["dataset"],
        "question": item.input["question"],
        "sql": item.expected_output["sql"],
    }
    return evaluate_case(case)


def execution_accuracy(*, output, **kwargs):
    return Evaluation(name="execution_accuracy", value=1.0 if output["outcome"] == "correct" else 0.0,
                      comment=f"{output['outcome']}: {output.get('reason', '')}")


def valid_sql(*, output, **kwargs):
    return Evaluation(name="valid_sql", value=0.0 if output["outcome"] == "no_working_sql" else 1.0)


def average(name):
    def run_evaluator(*, item_results, **kwargs):
        values = [e.value for r in item_results for e in r.evaluations if e.name == name]
        return Evaluation(name=f"avg_{name}", value=sum(values) / len(values) if values else None)
    return run_evaluator


def main():
    parser = argparse.ArgumentParser(description="Run the SQL eval as a Langfuse experiment.")
    parser.add_argument("--run-name", help="label for this run (default: model + time)")
    args = parser.parse_args()

    langfuse = get_client()
    cases = read_cases(SEED_FILE) + read_cases(CASES_FILE)
    upload_cases(langfuse, cases)

    run_name = args.run_name or f"{SQL_MODEL}-{datetime.now():%Y%m%d-%H%M}"
    print(f"Running experiment '{run_name}' with {SQL_MODEL}. This asks the local model once per case.\n")

    dataset = langfuse.get_dataset(DATASET)
    result = dataset.run_experiment(
        name="TableTalk SQL eval",
        run_name=run_name,
        description=f"Execution accuracy with {SQL_MODEL}",
        task=task,
        evaluators=[execution_accuracy, valid_sql],
        run_evaluators=[average("execution_accuracy"), average("valid_sql")],
        max_concurrency=1,                     # one at a time: Ollama runs one model locally
        metadata={"sql_model": SQL_MODEL},
    )
    print(result.format())
    langfuse.flush()
    print("\nOpen http://localhost:3000, then Datasets > tabletalk-sql > Runs to compare runs.")


if __name__ == "__main__":
    main()
