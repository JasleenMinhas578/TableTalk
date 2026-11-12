# TableTalk: Project Plan

Last updated: Nov 11, 2026

## Overview

The goal is a web app, running fully on a MacBook M4 Pro (24 GB RAM), that turns plain-English questions about a user's own data into SQL, with no paid or external APIs.

A user's journey:

1. Upload up to 5 Excel or CSV tables, or pick one of 3 sample datasets (online shop, bank card fraud, school results).
2. See every table, its columns and how tables connect on an interactive data map.
3. Ask questions in chat, in English or Hinglish. The router decides whether it is a data question, a question about the tables, small talk, or off-topic. Answers stream in live.
4. Rephrase a vague question with one click, using the real column names.
5. In the playground, let AI write the SQL or write it yourself, run it, fix it, and save correct ones as test cases.

Every step is traced in Langfuse, and both the router and the SQL agent are measured with repeatable evals. Code: github.com/JasleenMinhas578/TableTalk.

## Progress

Everything in the original plan is built, and the website is running; the next steps are running the SQL eval and editable data-map links.

| Part | Status | Where it lives |
| --- | --- | --- |
| Local setup (Ollama, uv, self-hosted Langfuse) | Done | Ollama app, `.env`, Langfuse in Docker |
| Upload, session reuse, 5-table limit, old-session cleanup | Done | `app/ingest.py` |
| 3 sample datasets | Done | `scripts/make_sample_datasets.py`, `app/samples.py` |
| Schema profiling and relationship inference | Done | `app/schema.py` |
| SQL agent (write, check, run, retry, fix mode, review) | Done | `app/agent/sql_agent.py` |
| Hybrid router | Done, 99% on golden set | `app/agent/router.py` |
| Main graph with streaming answers | Done | `app/agent/main_graph.py` |
| Rephrasing with a detail-keeping check | Done | `app/agent/rephrase.py` |
| API | Done | `app/main.py` |
| Website (upload, data map, chat, playground) | Done, running | `frontend/` |
| Automated tests (about 60) | Done | `tests/` |
| SQL eval (local and Langfuse experiment) | Built, not yet run | `evals/` |
| README with diagrams and screenshots | Done | `README.md` |
| Editable data-map links | Future | see Future plan |
| Docker + free public link (Hugging Face Space) | Planned | see Deployment |

## Tech stack

Everything is free and runs locally. Ollama serves the models because vLLM is built mainly for NVIDIA GPUs and is not a good fit for a Mac.

| Layer | Choice | Why |
| --- | --- | --- |
| Model server | Ollama | One-command setup on Apple Silicon; models load automatically when called |
| SQL model | Qwen2.5-Coder 7B | Strong at SQL for its size; about 5 GB, runs fully on the M4 Pro GPU |
| Small model (router fallback, splitting, chat replies) | Llama 3.2 3B | Fast for short tasks |
| Embeddings | nomic-embed-text | Feeds the intent classifier |
| Intent classifier | scikit-learn logistic regression, saved with joblib | Fast, consistent, easy to retrain |
| Agent orchestration | LangGraph | Two graphs: the main graph and the SQL sub-graph |
| SQL safety | sqlglot | Parses SQL without running it: one SELECT only, real tables only |
| Observability | Langfuse, self-hosted with Docker | Free; every graph step in one trace |
| Data engine | DuckDB | One `.duckdb` file per upload session |
| File parsing | pandas + openpyxl | One table per sheet |
| Python tooling | uv, pytest, httpx | Fast installs; tests for ingest, SQL safety and the API |
| Backend | FastAPI + python-multipart | File uploads and JSON endpoints |
| Frontend | React + Vite | Fast dev server that forwards `/api` to FastAPI |
| Frontend libraries | React Flow + dagre, CodeMirror, react-dropzone, sonner, lucide | Data map, SQL editor with autocomplete, drag-and-drop upload, toasts, icons |

Why not vLLM: it is a high-throughput server for many users on NVIDIA GPUs. If the app later moves to a GPU server, swapping Ollama for vLLM needs only an endpoint change, since both speak the OpenAI API format.

## Upload and schema

Each uploaded sheet becomes one DuckDB table, and relationships between tables are inferred automatically, then shown as an ER diagram the user can correct.

1. **Ingest.** Read each file with pandas. Every sheet becomes a table named after the file and sheet. Clean column names to snake\_case and let DuckDB infer types (dates, numbers, text).
2. **Profile.** For each column, store type, null count, distinct count and 3 sample values. This profile is also what the LLM sees as schema context.
3. **Find keys.** A column is a likely primary key if its values are unique and not null (for example `customer_id`).
4. **Infer relationships.** Link a column in one table to a key in another when the names match (`orders.customer_id` to `customers.customer_id`) and most values overlap. Mark each link with a confidence score.
5. **Draw the ER diagram.** React Flow shows tables as cards and relationships as edges. Users can add, delete or fix links; their edits override the inferred ones.

**What was added while building:**

- **One session per set of files.** The session ID is a hash of the file contents, so uploading the same files again reopens the existing database instead of creating a duplicate.
- **A 5-table limit.** At most 5 files and 5 tables per upload. Everything is counted before the database is created, so a rejected upload leaves nothing behind.
- **Sample datasets.** Online shop (30 customers, 10 products, 100 orders), bank card fraud (40 accounts, 12 merchants, 300 transactions, 22 fraud) and school results (40 students, 8 courses, 160 enrollments), each with 3 linked sheets.
- **Automatic cleanup.** Sessions unused for 7 days are deleted at startup (`TABLETALK_SESSION_DAYS`, 0 keeps them forever); opening a session resets its clock.
- **Safe session IDs.** The API only accepts 32-character hex IDs.

## Hybrid intent router

The router sorts every message into one of four intents using three layers, cheapest first, so the LLM is only called when the cheaper layers are unsure.

1. **Rules.** Regex and keyword checks catch obvious cases: greetings and thanks, or aggregation words (total, average, count, show me) appearing next to a real table or column name.
2. **Classifier.** Embed the message with nomic-embed-text and classify it with logistic regression. Accept the answer if confidence is at least 0.8 (tune this on your eval set).
3. **LLM fallback.** Below that threshold, ask the 3B model to pick one intent, giving it the schema summary and a strict JSON output format.

| Intent | Example | What happens |
| --- | --- | --- |
| SQL question | "What were total sales in March?" | Goes to the SQL path |
| Dataset question | "What tables do I have?" | Answered from the schema profile, no SQL |
| Small talk | "Hi", "thanks" | Short friendly reply |
| Off-topic | "What's the weather?" | Polite refusal: "I can only help with your uploaded data." |

Pasted SQL is caught by the rules layer: a message counts as SQL when it contains SELECT (or a real WITH clause) followed by FROM. A message can mix SQL and a question, even on one line; it is split by a semicolon or line break first, and by the 3B model only when that fails, with sqlglot confirming the result.

### Training data

| File | Used for | Size |
| --- | --- | --- |
| `training/router_examples.csv` | Training | 195 template-based examples |
| `training/router_augmented.csv` | Training | 948 paraphrases written by Qwen, 5 per example |
| `training/router_hard.csv` | Training | 256 hand-written boundary cases, including Hinglish |
| `training/router_golden_eval.csv` | Testing only, never trained on | 90 hand-written messages |

The hard examples cover the boundaries the router got wrong: Hinglish ("kitne orders aaye"), numbers about the outside world (GDP, population, percentages) as off-topic, and questions about the assistant as small talk.

### How it is trained and tested

- **5-fold cross-validation** with `StratifiedGroupKFold`: every example is tested once, each fold keeps the same mix of intents, and a sentence always stays in the same fold as its paraphrases, so there is no leakage.
- **Class imbalance** (sql 505 vs small talk 174) is handled with `class_weight="balanced"`.
- **Regularisation** (`C`) is tuned automatically by cross-validated macro F1.
- **Embeddings are cached** in `models/embedding_cache.joblib`, so retraining takes seconds.
- **Golden eval** is the score to trust, followed by a threshold sweep.

### Results

| Run | Golden accuracy | Decided by classifier at 0.8 | Sent to LLM |
| --- | --- | --- | --- |
| Before hard examples | 90% | 43 of 90, all correct | 47 |
| With 256 hard examples | 99% | 83 of 90, all correct | 7 |

The threshold stays at **0.8**. At 0.7, the one remaining mistake ("sabse zyada kharcha kisne kiya" read as off-topic) would be decided without the LLM, to save only 2 calls. The golden set and the hard examples were written by the same author, so 99% is likely optimistic; real messages from Langfuse are the next test.

## LangGraph agent flow

There are two LangGraph graphs: the main graph (`main_graph.py`) routes each message to one of four paths, and only data questions enter the SQL agent (`sql_agent.py`), which checks, runs, repairs and reviews the query.

_The agent flow diagram is in the README ("Inside the SQL agent")._

- **Fix mode.** If the message contains SQL, it skips writing and goes straight to the check. Qwen only steps in when the check or the run fails, and the website shows the user's SQL next to the fixed version.
- **Check with sqlglot** before anything runs: exactly one SELECT or WITH query, only tables that exist (names from WITH clauses allowed), no file-reading functions.
- **Retry loop.** A failed check or run sends the SQL and the error back to Qwen, up to 3 retries. After that the agent stops and returns the error, so the user can fix it in the playground.
- **Review.** Qwen sees the question, the SQL and the first 5 rows, and answers in JSON whether they match, with a suggested fix. It only suggests; the user decides.
- **Explain.** The 3B model turns the rows into one or two plain sentences, using only the numbers shown.
- **One trace.** The Langfuse handler is passed into the sub-graph, so every step of a question shows up in one trace. A generated picture of the graph is saved in `docs/sql_agent_graph.md`.

## Rephrasing

Rephrasing is built (`app/agent/rephrase.py`, `POST /rephrase`). The user clicks Rephrase in chat and sees a suggestion with "Use this"; nothing is replaced automatically.

1. **Skip it when it can't help.** Pasted SQL, small talk and off-topic messages get a short reason instead.
2. **Rewrite with the schema.** Llama 3.2 3B (JSON mode) gets the tables and columns and strict rules: keep every number, name, date and filter, never add filters, keep "last month" as it is.
3. **Ask when unclear.** If the question is too vague, it returns a clarifying question instead.
4. **Check the rewrite.** Numbers, quoted words and names must all survive (whole-word match). If anything was dropped, the rewrite is rejected and the original stays.
5. **Tested** in `tests/test_rephrase.py`.

## SQL playground

The playground tab lets people write SQL themselves or have AI write it, then run, fix and save it.

- **Ask AI to write the query:** describe it in English; `POST /generate-sql` checks with the router that it is a data question, runs the SQL agent, puts the SQL in the editor and runs it.
- **Editor:** CodeMirror with autocomplete for the user's own tables and columns; Cmd + Enter runs it.
- **Run:** `POST /run-sql` runs the same sqlglot checks as the agent, with no AI.
- **Results:** a table of the first 100 rows with row numbers; the real total is counted, and a note appears when rows are hidden.
- **Fix my SQL:** sends the editor's SQL through fix mode and shows the suggestion with "Use this and run" or "Keep mine".
- **SQL test set:** after a run, "Save as a test case" stores the question and SQL in `evals/sql_cases.jsonl`, the SQL eval's answer key.
- **Recent runs:** the last 8 queries, one click to reload.

Safety: only one read-only SELECT (or WITH) query, only known tables, no file-reading functions, a read-only DuckDB connection.

## Website

The website lives in `frontend/` (React + Vite) and talks to FastAPI through a `/api` proxy, so it runs with `npm run dev` beside `uvicorn`.

| Screen | What the user can do |
| --- | --- |
| Home | Drag in up to 5 files, pick a sample dataset, or reopen a recent session |
| Tables sidebar | Browse tables, row counts, columns, friendly types, keys and links; preview a table in one click |
| Ask | Chat with starter questions from their own tables; live steps, intent badge, SQL, result table and an answer streamed word by word; Rephrase button |
| Data map | Interactive ER diagram: click a table to highlight its links, drag, zoom, mini-map |
| Playground | AI writes SQL or you do; run, fix, and save test cases |

Each screen has its own address (`/s/<session>/map` and so on), so the browser's Back button works, and recent sessions are remembered in the browser.

**Look:** graph-paper background like spreadsheet cells, a small mascot (a spreadsheet shaped like a speech bubble) that reacts while it thinks, and one colour per intent: purple for data queries, green for questions about the data, yellow for chat, pink for out of scope.

## Observability with Langfuse

Self-hosted Langfuse records every request end to end, for free, with all data staying on your Mac. LangSmith is skipped because it is mainly a paid hosted service.

- **Setup:** Langfuse runs from its Docker Compose file; the callback handler is passed into every LangGraph run, including the SQL sub-graph, so one question is one trace.
- **What is traced:** routed intent and layer, prompts, generated SQL, each retry and error, review, rephrasing and timing.
- **Experiments:** `evals/langfuse_eval.py` uploads the test cases as the dataset `tabletalk-sql` and runs them as an experiment, storing `execution_accuracy` and `valid_sql` scores, so runs (for example 7B vs 14B) are compared side by side.

## Evals

The main measure is execution accuracy: run the generated SQL and the reference SQL, and count it correct only when both return the same rows.

| Metric | What it measures | How |
| --- | --- | --- |
| Execution accuracy | Is the answer right? | Compare result sets (ignore row order unless the question asks for sorting) |
| Valid SQL rate | Does the query run at all? | Share of queries that execute without error |
| Router accuracy | Is the intent correct? | Precision and recall per intent on a labeled message set |
| Off-topic refusal rate | Does it stay in scope? | Share of off-topic messages correctly refused |
| Self-repair rate | Does the retry loop help? | Share of failed first attempts fixed within 3 retries |
| Latency | Is it fast enough? | Median and 95th percentile time per request |

**Eval data:**

- Start with 2 or 3 sample datasets of your own (for example sales, HR, inventory) and about 50 question-and-SQL pairs each, from easy (one table) to hard (joins, grouping, dates).
- For a general check, run a subset of the public Spider or BIRD benchmarks.
- Add corrected queries from the test area over time.

Run the full suite with a script after every change to the model, prompt or router, and log results to Langfuse.

**Done so far:**

- **Router eval:** 5-fold grouped cross-validation plus a 90-message golden set never used for training: 99% accuracy, 7 of 90 messages sent to the LLM.
- **SQL eval (built, not yet run):** `uv run python -m evals.run_sql_eval`, or `evals.langfuse_eval` for a Langfuse experiment.
  1. Test cases: 24 seed cases (8 per sample) plus any saved from the playground.
  2. Run the correct SQL to get the answer key.
  3. Ask the agent the question, timing it and counting retries.
  4. Compare results, not SQL text: same row count, every correct column present with the same values, extra columns allowed, order ignored, numbers rounded to 2 decimals.
  5. Report execution accuracy, valid SQL rate, first-try rate, self-repair rate and time, overall and per dataset.
- **Automated tests** (`uv run pytest`, about 60): uploads, samples, schema, every blocked SQL pattern, the API, the eval matching rules, rephrasing and cleanup.

**Next:** run the SQL eval with Qwen 7B, then 14B (`TABLETALK_SQL_MODEL=qwen2.5-coder:14b`), and record both in the README.

## Build phases

All planned phases are built; only running the SQL eval is left from the original plan.

- [x] Phase 1: Foundations (Ollama, models, Langfuse, uv project)
- [x] Phase 2: Data layer (upload, DuckDB, profiling, relationships, limits, samples)
- [x] Phase 3: SQL agent (write, sqlglot check, run, repair loop, fix mode, review)
- [x] Phase 4: Router and chat (rules, classifier, LLM fallback, main graph, streaming)
- [x] Phase 5: Router evals (golden set, 90% to 99%)
- [x] Phase 6: Website (upload, data map, chat, playground, routes)
- [x] Phase 7: SQL evals and Langfuse experiments (built; first run pending)
- [x] Phase 8: Rephrasing with a safety check
- [x] Phase 9: Old-session cleanup, model setting, README with diagrams

## Future plan

- **Editable data-map links:** let users add, remove and fix relationships on the data map when the automatic guess is wrong (for example `cust_id` vs `id`), with their changes saved per session and used by the SQL agent.
- **Run and record the SQL eval** for Qwen 7B vs 14B, and add the results to the README.
- **Grow the golden sets from real use:** label real messages and queries from Langfuse and add them to the router and SQL test sets (never to training).
- **More file types:** Parquet and JSON uploads.
- **Charts on request:** an optional chart view only when the user asks for one.

## Deployment: run anywhere, share a free public link

The same code runs in three ways, and only the settings change. It costs nothing: no paid APIs and no GPU.

| Mode | Who it's for | How it starts | Models |
| --- | --- | --- | --- |
| Local | Me, on my Mac | uv + Ollama + npm dev server | qwen2.5-coder:7b, llama3.2:3b |
| Docker | Anyone, on their own laptop (8–16 GB RAM) | `docker compose up`, open localhost:8000 | Same as local |
| Hugging Face Space | Anyone, through a public link | Free CPU Space (2 vCPU, 16 GB RAM) | qwen2.5-coder:3b, llama3.2:3b |

**Space description:** TableTalk: upload a spreadsheet and ask questions about it in plain English or Hinglish. A local AI writes and runs the SQL for you.

### Build steps (handed to Claude Code)

1. Move every model name, Ollama URL and data path into `app/config.py`, read from .env.
2. Let FastAPI serve the built React frontend, so one port runs the whole app.
3. Write a multi-stage Dockerfile (Node builds the frontend, Python with uv runs the app).
4. Write docker-compose.yml: Ollama plus the app, with models pulled on first start.
5. Add `deploy/hf-space/`: one container running Ollama and the app on port 7860, with lighter models.
6. Add .env.example with local, Docker and cloud profiles, and update the README's "Run it" section.
7. Keep `uv run pytest` passing and the local flow unchanged.

### Creating the Hugging Face Space

1. Make a free account on huggingface.co.
2. Create a Space: New Space, type Docker, free CPU hardware, public.
3. Create an access token with write permission under Settings, then Access Tokens.
4. Copy `deploy/hf-space/` into the Space's git repo, commit, and push, using the token as the password.
5. Watch the build logs. The first build takes a few minutes because it downloads the models.
6. Share the link: huggingface.co/spaces/\<your-name>/tabletalk.

### Limits of the free tier

- Answers take roughly 20–60 seconds on CPU.
- The Space sleeps when idle, so the first visitor waits while it wakes up.
- Uploaded files are not kept, which is fine for a demo.
- For live interviews, a Cloudflare Tunnel from the Mac gives a fast link while the Mac is on.
