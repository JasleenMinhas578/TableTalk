import json
from contextlib import asynccontextmanager
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.main_graph import chat, chat_stream
from app.agent.rephrase import rephrase
from app.agent.router import route
from app.agent.sql_agent import ask, check_sql, run_sql
from app.eval_cases import add_case, delete_case, list_cases
from app.ingest import DATA_DIR, MAX_TABLES, TooManyTables, cleanup_old_sessions, ingest_files
from app.samples import list_samples, sample_path
from app.schema import get_schema

@asynccontextmanager
async def lifespan(app):
    removed = cleanup_old_sessions()      # sessions untouched for TABLETALK_SESSION_DAYS (default 7)
    if removed:
        print(f"Removed {removed} old session(s)")
    yield


app = FastAPI(title="TableTalk", lifespan=lifespan)

# Let the React frontend (running on another port) call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED = {".xlsx", ".xlsm", ".csv"}
MAX_ROWS_RETURNED = 100   # rows sent to the website; total_rows says how many exist


# ---------- helpers ----------

def db_path_for(session_id: str) -> Path:
    # Only allow plain hex IDs, so nobody can reach other files
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise HTTPException(400, "Invalid session id")
    path = DATA_DIR / f"{session_id}.duckdb"
    if not path.exists():
        raise HTTPException(404, "Session not found")
    path.touch()   # mark as recently used, so the automatic cleanup keeps it
    return path


# ---------- request bodies ----------

class ChatRequest(BaseModel):
    session_id: str
    message: str


class GenerateRequest(BaseModel):
    session_id: str
    question: str


class RephraseRequest(BaseModel):
    session_id: str
    message: str


class TestCaseRequest(BaseModel):
    session_id: str
    question: str
    sql: str


class RunSQLRequest(BaseModel):
    session_id: str
    sql: str


# ---------- endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    if len(files) > MAX_TABLES:
        raise HTTPException(400, f"Upload at most {MAX_TABLES} files at a time.")
    with tempfile.TemporaryDirectory() as tmp:
        saved = []
        for f in files:
            suffix = Path(f.filename).suffix.lower()
            if suffix not in ALLOWED:
                raise HTTPException(400, f"Unsupported file: {f.filename}")
            dest = Path(tmp) / Path(f.filename).name
            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)
            saved.append(dest)
        try:
            result = await run_in_threadpool(ingest_files, saved)
        except TooManyTables as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Could not read file: {e}")
    return {
        "session_id": result["session_id"],
        "reused": result.get("reused", False),
        "tables": result["tables"],
    }


@app.get("/samples")
def samples():
    """The sample datasets shown on the upload screen."""
    return list_samples()


@app.post("/samples/{sample_id}")
async def load_sample(sample_id: str):
    """Load a sample dataset, so people can try TableTalk without their own file."""
    path = sample_path(sample_id)
    if path is None:
        raise HTTPException(404, f"No sample called '{sample_id}'.")
    if not path.exists():
        raise HTTPException(404, "Sample data not found. Create it with: uv run python -m scripts.make_sample_datasets")
    result = await run_in_threadpool(ingest_files, [path])
    return {
        "session_id": result["session_id"],
        "reused": result.get("reused", False),
        "tables": result["tables"],
    }


@app.get("/schema/{session_id}")
def schema(session_id: str):
    return get_schema(str(db_path_for(session_id)))


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message is empty")
    db_path = str(db_path_for(req.session_id))
    # The models are slow, so run in a thread and keep the server responsive
    result = await run_in_threadpool(chat, db_path, req.message)
    rows = result.get("rows", [])
    return {
        "intent": result.get("intent"),
        "route": result.get("route_info"),
        "answer": result.get("answer"),
        "sql": result.get("sql"),
        "original_sql": result.get("original_sql"),
        "columns": result.get("columns", []),
        "rows": rows[:MAX_ROWS_RETURNED],
        "total_rows": result.get("total_rows", len(rows)),
        "row_limit": MAX_ROWS_RETURNED,
        "review": result.get("review"),
        "error": result.get("error"),
    }


@app.post("/generate-sql")
async def generate_sql_endpoint(req: GenerateRequest):
    """Playground helper: turn a plain-English request into SQL (no chat explanation)."""
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Describe what you want the query to find.")
    db_path = str(db_path_for(req.session_id))
    schema = get_schema(db_path)
    intent = (await run_in_threadpool(route, question, schema))["intent"]
    if intent not in ("sql", "dataset"):
        raise HTTPException(400, "That doesn't look like a question about your data. Try something like "
                                 "\"total orders per month\".")
    result = await run_in_threadpool(ask, db_path, question)
    return {"sql": result.get("sql"), "error": result.get("error"), "review": result.get("review")}


@app.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest):
    """Like /chat, but sends progress and the answer word by word (Server-Sent Events)."""
    if not req.message.strip():
        raise HTTPException(400, "Message is empty")
    db_path = str(db_path_for(req.session_id))

    def events():
        try:
            for event in chat_stream(db_path, req.message, MAX_ROWS_RETURNED):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/rephrase")
async def rephrase_endpoint(req: RephraseRequest):
    """Suggest a clearer version of a vague question. The user decides whether to use it."""
    if not req.message.strip():
        raise HTTPException(400, "Type a question first.")
    schema = get_schema(str(db_path_for(req.session_id)))
    return await run_in_threadpool(rephrase, req.message, schema)


@app.post("/run-sql")
def run_sql_endpoint(req: RunSQLRequest):
    db_path = str(db_path_for(req.session_id))
    schema = get_schema(db_path)
    state = {
        "db_path": db_path,
        "sql": req.sql.strip().rstrip(";"),
        "tables": [t.lower() for t in schema["tables"]],
        "retries": 0,
    }
    checked = check_sql(state)          # same safety checks as the agent
    if checked.get("error"):
        raise HTTPException(400, checked["error"])
    result = run_sql(state)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    rows = result["rows"]
    return {
        "columns": result["columns"],
        "rows": rows[:MAX_ROWS_RETURNED],
        "total_rows": result.get("total_rows", len(rows)),
        "row_limit": MAX_ROWS_RETURNED,
    }


# ---------- SQL test set (used by evals/run_sql_eval.py) ----------

@app.get("/test-cases/{session_id}")
def get_test_cases(session_id: str):
    db_path_for(session_id)
    return list_cases(session_id)


@app.post("/test-cases")
def create_test_case(req: TestCaseRequest):
    """Save a question with SQL the user checked is correct."""
    if not req.question.strip():
        raise HTTPException(400, "Add the question this SQL answers.")
    db_path = str(db_path_for(req.session_id))
    schema = get_schema(db_path)
    state = {"db_path": db_path, "sql": req.sql.strip().rstrip(";"),
             "tables": [t.lower() for t in schema["tables"]], "retries": 0}
    checked = check_sql(state)
    if checked.get("error"):
        raise HTTPException(400, f"Only working, read-only SQL can be saved: {checked['error']}")
    return add_case(req.session_id, req.question, req.sql)


@app.delete("/test-cases/{case_id}")
def remove_test_case(case_id: str):
    if not delete_case(case_id):
        raise HTTPException(404, "Test case not found.")
    return {"deleted": case_id}
