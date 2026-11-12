# SQL evals

Measures how often the AI writes SQL that gives the **right answer**.

## Run it

```bash
uv run python -m evals.run_sql_eval                  # all test cases
uv run python -m evals.run_sql_eval --dataset fraud  # one dataset
uv run python -m evals.run_sql_eval --limit 5        # quick check
```

Ollama must be running. Each case asks the local model, so expect several seconds per case.

## Compare models

```bash
TABLETALK_SQL_MODEL=qwen2.5-coder:14b uv run python -m evals.run_sql_eval
```

Pull the model first with `ollama pull qwen2.5-coder:14b`. Each report is saved with the model name.

## In Langfuse

```bash
uv run python -m evals.langfuse_eval --run-name qwen-7b
```

Uploads the test cases as the Langfuse dataset `tabletalk-sql`, runs them as an experiment, and stores
`execution_accuracy` and `valid_sql` scores on every trace. In Langfuse (localhost:3000), open
**Datasets > tabletalk-sql > Runs** to compare runs side by side and click into any failed question.

## Files

| File | What it is |
| --- | --- |
| `seed_cases.jsonl` | 24 starter cases, 8 per sample dataset, written by hand |
| `sql_cases.jsonl` | Cases you save from the playground ("Save as a test case") |
| `compare.py` | The rules for deciding whether two results match |
| `run_sql_eval.py` | Runs every case and prints the scores |
| `langfuse_eval.py` | The same eval as a Langfuse experiment |
| `results/` | A full JSON report from every run, to compare runs over time |

## Scores

| Score | Meaning |
| --- | --- |
| Execution accuracy | Share of questions where the AI's result matched the correct result. The main number. |
| Valid SQL rate | Share where the AI produced SQL that ran at all |
| First-try rate | Share that worked without any retry |
| Self-repair rate | Of the cases that hit an error, the share the retry loop fixed |
| Time per question | Median and 95th percentile seconds |

## How a result counts as correct

We compare what the queries return, never the SQL text:

1. Same number of rows.
2. Every column of the correct answer appears in the AI's answer with the same values (names don't matter).
3. Extra AI columns are fine.
4. Row order doesn't matter.
5. Numbers are rounded to 2 decimals.

## Good habits

- Only save a playground query as a test case after checking the result is right.
- Keep test cases out of any prompt or training data, or the score stops meaning anything.
- Run the eval after every change to the model, prompts or agent, and compare with the last report.
