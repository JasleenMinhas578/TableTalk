import json
import os
import re
from typing import TypedDict

import duckdb
import sqlglot
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, StateGraph
from sqlglot import exp

from app.schema import get_schema

load_dotenv()

# ---------- settings ----------

MAX_RETRIES = 3
# Change these in .env to compare models, e.g. TABLETALK_SQL_MODEL=qwen2.5-coder:14b
SQL_MODEL = os.getenv("TABLETALK_SQL_MODEL", "qwen2.5-coder:7b")
SMALL_MODEL = os.getenv("TABLETALK_SMALL_MODEL", "llama3.2:3b")

llm = ChatOllama(model=SQL_MODEL, temperature=0)                      # writes and fixes SQL
reviewer = ChatOllama(model=SQL_MODEL, temperature=0, format="json")  # checks the logic
splitter = ChatOllama(model=SMALL_MODEL, temperature=0, format="json")  # splits SQL from question

BLOCKED_FUNCS = re.compile(r"read_csv|read_parquet|read_json|read_text|glob\s*\(|getenv", re.I)
# Where SQL starts: SELECT, or a CTE like "WITH x AS ("
SQL_START = re.compile(r"\bselect\b|\bwith\s+\w+\s+as\s*\(", re.I)
QUESTION_WORDS = re.compile(
    r"\b(what|why|how|is|are|does|can|which|show|give|correct|right)\b|\?", re.I
)


class SQLState(TypedDict, total=False):
    question: str
    db_path: str
    mode: str                # "generate" or "fix"
    user_sql: str
    schema_text: str
    tables: list[str]
    sql: str
    error: str | None
    retries: int
    columns: list[str]
    rows: list[list]
    total_rows: int          # how many rows the query really returns
    review: dict


# ---------- helpers ----------

def schema_to_text(schema: dict) -> str:
    lines = []
    for table, info in schema["tables"].items():
        cols = ", ".join(
            f'{c["name"]} {c["type"]} (e.g. {", ".join(c["samples"][:2])})'
            for c in info["columns"]
        )
        lines.append(f"TABLE {table} ({info['rows']} rows): {cols}")
    for r in schema["relationships"]:
        lines.append(f"JOIN {r['from_table']}.{r['from_column']} = {r['to_table']}.{r['to_column']}")
    return "\n".join(lines)


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


def fail(state: SQLState, message: str) -> dict:
    return {"error": message, "retries": state.get("retries", 0) + 1}


def parses_as_query(sql: str) -> bool:
    try:
        return isinstance(sqlglot.parse_one(sql, read="duckdb"), exp.Query)
    except sqlglot.errors.ParseError:
        return False


def split_sql_and_question(text: str) -> tuple[str | None, str]:
    """Return (sql, question). sql is None when the message has no SQL."""
    text = text.strip()
    m = SQL_START.search(text)
    if not m or not re.search(r"\bfrom\b", text[m.start():], re.I):
        return None, text                                   # plain question

    before, rest = text[:m.start()].strip(), text[m.start():].strip()

    # 1. A semicolon or line break ends the query
    for sep in (";", "\n"):
        if sep in rest:
            sql, after = rest.split(sep, 1)
            if parses_as_query(sql.strip()):
                return sql.strip(), f"{before} {after}".strip()

    # 2. Parses and has no question words: it's just SQL
    whole = rest.rstrip(";").strip()
    whole_ok = parses_as_query(whole)
    if whole_ok and not QUESTION_WORDS.search(whole):
        return whole, before

    # 3. Hard case: ask the small model, then verify with sqlglot
    prompt = (
        "The text below contains a SQL query and maybe a question about it, "
        "possibly on the same line. Separate them exactly, without changing any words.\n"
        f"Text: {text}\n"
        'Reply in JSON: {"sql": "the SQL query", "question": "the question or empty"}'
    )
    try:
        out = json.loads(splitter.invoke(prompt).content)
        sql = str(out.get("sql", "")).strip().rstrip(";").strip()
        question = str(out.get("question", "")).strip()
        if sql and parses_as_query(sql):
            return sql, question
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    # 4. Fallback: treat it all as SQL; fix mode will repair it
    return whole, before


# ---------- nodes ----------

def load_schema(state: SQLState) -> dict:
    schema = get_schema(state["db_path"])
    update = {
        "schema_text": schema_to_text(schema),
        "tables": [t.lower() for t in schema["tables"]],
        "retries": 0,
        "error": None,
    }
    if state.get("mode") == "fix" and state.get("user_sql"):
        update["sql"] = extract_sql(state["user_sql"])
    return update


def generate_sql(state: SQLState) -> dict:
    question = state.get("question") or "Keep the original intent of the user's query."
    prompt = (
        "You write DuckDB SQL. Use only these tables and columns:\n"
        f"{state['schema_text']}\n\n"
        f"Question: {question}\n"
    )
    if state.get("error"):
        prompt += (
            f"\nThis query:\n{state.get('sql', '')}\n"
            f"failed with this error:\n{state['error']}\n"
            "Fix the query.\n"
        )
    prompt += "Return exactly one SELECT query inside a ```sql block, nothing else."
    reply = llm.invoke(prompt)
    return {"sql": extract_sql(reply.content)}


def check_sql(state: SQLState) -> dict:
    """Static checks with sqlglot before anything runs."""
    sql = state.get("sql", "")
    if BLOCKED_FUNCS.search(sql):
        return fail(state, "File or system functions are not allowed.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        return fail(state, f"Syntax error: {e}")

    if len(statements) != 1:
        return fail(state, "Exactly one statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        return fail(state, "Only read-only SELECT queries are allowed.")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used = {t.name.lower() for t in tree.find_all(exp.Table)} - cte_names
    unknown = used - set(state["tables"])
    if unknown:
        return fail(state, f"Unknown table(s): {', '.join(sorted(unknown))}. "
                           f"Available: {', '.join(state['tables'])}")
    return {"error": None}


MAX_FETCH = 1000   # rows fetched for the agent; the API shows fewer


def run_sql(state: SQLState) -> dict:
    try:
        con = duckdb.connect(state["db_path"], read_only=True)
        try:
            total = con.execute(f"SELECT COUNT(*) FROM ({state['sql']}) AS q").fetchone()[0]
            cur = con.execute(f"SELECT * FROM ({state['sql']}) AS q LIMIT {MAX_FETCH}")
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchall()]
        finally:
            con.close()
        return {"columns": columns, "rows": rows, "total_rows": total, "error": None}
    except Exception as e:
        return fail(state, str(e))


def review_sql(state: SQLState) -> dict:
    """Ask the model whether the query really answers the question."""
    if not state.get("question"):
        return {"review": {"matches": True, "issue": "", "suggested_sql": None}}
    sample = json.dumps(state["rows"][:5], default=str)
    prompt = (
        "You review SQL for correctness.\n"
        f"Schema:\n{state['schema_text']}\n\n"
        f"Question: {state['question']}\n"
        f"SQL:\n{state['sql']}\n"
        f"Columns: {state['columns']}\nFirst rows: {sample}\n\n"
        'Reply in JSON: {"matches": true or false, "issue": "short reason or empty", '
        '"suggested_sql": "fixed query or null"}'
    )
    try:
        review = json.loads(reviewer.invoke(prompt).content)
    except (json.JSONDecodeError, TypeError):
        review = {"matches": None, "issue": "Review could not be parsed.", "suggested_sql": None}
    return {"review": review}


# ---------- routing ----------

def start_route(state: SQLState) -> str:
    return "check" if state.get("mode") == "fix" and state.get("sql") else "generate"


def after_check(state: SQLState) -> str:
    if not state.get("error"):
        return "run"
    return "retry" if state["retries"] <= MAX_RETRIES else "give_up"


def after_run(state: SQLState) -> str:
    if not state.get("error"):
        return "review"
    return "retry" if state["retries"] <= MAX_RETRIES else "give_up"


# ---------- graph ----------

builder = StateGraph(SQLState)
builder.add_node("load_schema", load_schema)
builder.add_node("generate_sql", generate_sql)
builder.add_node("check_sql", check_sql)
builder.add_node("run_sql", run_sql)
builder.add_node("review_sql", review_sql)

builder.set_entry_point("load_schema")
builder.add_conditional_edges("load_schema", start_route,
                              {"generate": "generate_sql", "check": "check_sql"})
builder.add_edge("generate_sql", "check_sql")
builder.add_conditional_edges("check_sql", after_check,
                              {"run": "run_sql", "retry": "generate_sql", "give_up": END})
builder.add_conditional_edges("run_sql", after_run,
                              {"review": "review_sql", "retry": "generate_sql", "give_up": END})
builder.add_edge("review_sql", END)

sql_agent = builder.compile()


# ---------- entry point ----------

def ask(db_path: str, question: str = "", user_sql: str | None = None) -> dict:
    """Answer a question, or check and fix SQL the user typed (alone or with a question)."""
    if not user_sql:
        found_sql, rest = split_sql_and_question(question)
        if found_sql:
            user_sql, question = found_sql, rest

    state = {"db_path": db_path, "question": question,
             "mode": "fix" if user_sql else "generate"}
    if user_sql:
        state["user_sql"] = user_sql
    result = sql_agent.invoke(state, config={"callbacks": [CallbackHandler()]})
    result["original_sql"] = user_sql
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print('Usage: uv run python -m app.agent.sql_agent <db_path> "<question and/or SQL>"')
        sys.exit(1)

    result = ask(sys.argv[1], " ".join(sys.argv[2:]))
    print("Mode:", result.get("mode"))
    if result.get("question"):
        print("Question:", result["question"])
    if result.get("original_sql") and result.get("sql") != result["original_sql"]:
        print("Your SQL:\n", result["original_sql"])
        print("Fixed SQL:")
    else:
        print("SQL:")
    print(result.get("sql"))

    if result.get("error"):
        print("\nFailed after retries:", result["error"])
    else:
        print("\nColumns:", result["columns"])
        for row in result["rows"][:10]:
            print(row)
        print("\nReview:", result.get("review"))