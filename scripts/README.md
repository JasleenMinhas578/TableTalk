# Scripts

Run every script from the TableTalk folder with `uv run python -m scripts.<name>`.

| Script | What it makes | When to run it |
| --- | --- | --- |
| `make_sample_datasets` | The 3 sample spreadsheets in `samples/`: online shop, bank card fraud, school results | Once, or after changing the sample data |
| `make_router_data` | Starter router examples in `training/router_examples.csv` | Only if you want to rebuild the training data from scratch |
| `augment_router_data` | Paraphrases of those examples in `training/router_augmented.csv` (slow, uses Qwen; resumes if stopped) | After `make_router_data` |
| `draw_graph` | A picture of the SQL agent graph in `docs/sql_agent_graph.md` | After changing the agent graph |

Hand-written files that no script creates:

- `training/router_hard.csv`: boundary cases and Hinglish, used for training
- `training/router_golden_eval.csv`: the test set, never used for training

To retrain the router after changing any training file:

```bash
uv run python -m app.agent.router train
```
