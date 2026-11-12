import json
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, StateGraph

from app.agent.router import route
from app.agent.sql_agent import schema_to_text, split_sql_and_question, sql_agent
from app.schema import get_schema

load_dotenv()

chat_llm = ChatOllama(model="llama3.2:3b", temperature=0.3)

REFUSAL = ("Sorry, I can only help with the data you've uploaded. "
           "Try asking about your tables, like totals, trends or top items.")


class ChatState(TypedDict, total=False):
    message: str
    db_path: str
    schema: dict
    schema_text: str
    intent: str
    route_info: dict
    answer: str
    sql: str
    original_sql: str | None
    columns: list[str]
    rows: list[list]
    total_rows: int
    error: str | None
    review: dict


# ---------- nodes ----------

def load(state: ChatState) -> dict:
    schema = get_schema(state["db_path"])
    return {"schema": schema, "schema_text": schema_to_text(schema)}


def classify(state: ChatState) -> dict:
    info = route(state["message"], state["schema"])
    return {"intent": info["intent"], "route_info": info}


def answer_dataset(state: ChatState) -> dict:
    prompt = (
        "You describe the user's uploaded data. Answer ONLY from this schema; "
        "if the answer isn't in it, say so. Keep it short and plain.\n\n"
        f"{state['schema_text']}\n\nQuestion: {state['message']}"
    )
    return {"answer": chat_llm.invoke(prompt).content}


def small_talk(state: ChatState) -> dict:
    prompt = (
        "You are TableTalk, a friendly assistant that answers questions about the user's "
        "uploaded spreadsheets. Reply to this message in one or two short sentences, and "
        "gently invite a question about their data. Do not answer anything unrelated.\n\n"
        f"Message: {state['message']}"
    )
    return {"answer": chat_llm.invoke(prompt).content}


def refuse(state: ChatState) -> dict:
    return {"answer": REFUSAL}


def run_sql_agent(state: ChatState, config: RunnableConfig) -> dict:
    user_sql, question = split_sql_and_question(state["message"])
    sub_state = {"db_path": state["db_path"],
                 "question": question if user_sql else state["message"],
                 "mode": "fix" if user_sql else "generate"}
    if user_sql:
        sub_state["user_sql"] = user_sql
    # Passing config keeps the SQL steps inside the same Langfuse trace
    result = sql_agent.invoke(sub_state, config=config)
    return {
        "sql": result.get("sql"),
        "original_sql": user_sql,
        "columns": result.get("columns", []),
        "rows": result.get("rows", []),
        "total_rows": result.get("total_rows", len(result.get("rows", []))),
        "error": result.get("error"),
        "review": result.get("review", {}),
    }


def explain(state: ChatState) -> dict:
    if state.get("error"):
        return {"answer": "I couldn't get a working query for that. "
                          f"Last error: {state['error']}. You can edit the SQL in the playground."}
    if not state.get("rows"):
        return {"answer": "The query ran but returned no rows."}
    sample = json.dumps(state["rows"][:10], default=str)
    prompt = (
        "Explain this query result to a non-technical user in one or two sentences. "
        "Use only the numbers shown; do not invent any.\n\n"
        f"Question: {state['message']}\nColumns: {state['columns']}\n"
        f"Rows (first 10 of {len(state['rows'])}): {sample}"
    )
    return {"answer": chat_llm.invoke(prompt).content}


# ---------- graph ----------

def pick_path(state: ChatState) -> str:
    return state["intent"]


builder = StateGraph(ChatState)
builder.add_node("load", load)
builder.add_node("classify", classify)
builder.add_node("answer_dataset", answer_dataset)
builder.add_node("small_talk", small_talk)
builder.add_node("refuse", refuse)
builder.add_node("sql_agent", run_sql_agent)
builder.add_node("explain", explain)

builder.set_entry_point("load")
builder.add_edge("load", "classify")
builder.add_conditional_edges("classify", pick_path, {
    "sql": "sql_agent",
    "dataset": "answer_dataset",
    "small_talk": "small_talk",
    "off_topic": "refuse",
})
builder.add_edge("sql_agent", "explain")
for node in ("answer_dataset", "small_talk", "refuse", "explain"):
    builder.add_edge(node, END)

chat_graph = builder.compile()


def chat(db_path: str, message: str) -> dict:
    result = chat_graph.invoke({"db_path": db_path, "message": message},
                               config={"callbacks": [CallbackHandler()]})
    result.pop("schema", None)          # too big to send back
    result.pop("schema_text", None)
    return result


# ---------- streaming ----------

# Nodes whose words the user should see appear live
ANSWER_NODES = {"answer_dataset", "small_talk", "explain"}

STATUS = {
    "sql": "Writing and running SQL",
    "dataset": "Looking at your tables",
    "small_talk": "Writing a reply",
}


def chat_stream(db_path: str, message: str, row_limit: int = 100):
    """Run the graph and yield events as they happen, instead of one final answer.

    Events: {"type": "status"}, {"type": "intent"}, {"type": "sql"},
            {"type": "token"} (a few words of the answer), {"type": "done"}
    """
    yield {"type": "status", "text": "Understanding your question"}
    final = {}
    for mode, data in chat_graph.stream(
        {"db_path": db_path, "message": message},
        config={"callbacks": [CallbackHandler()]},
        stream_mode=["updates", "messages"],
    ):
        if mode == "messages":
            # Each LLM token arrives here; only pass on the ones from answer-writing nodes
            chunk, meta = data
            if meta.get("langgraph_node") in ANSWER_NODES and chunk.content:
                yield {"type": "token", "text": chunk.content}
            continue

        # "updates": a node finished; data = {node_name: what it returned}
        for node, update in data.items():
            if not update:
                continue
            final.update(update)
            if node == "classify":
                yield {"type": "intent", "intent": update["intent"], "route": update["route_info"]}
                if update["intent"] in STATUS:
                    yield {"type": "status", "text": STATUS[update["intent"]]}
            elif node == "sql_agent":
                rows = update.get("rows", [])
                yield {
                    "type": "sql",
                    "sql": update.get("sql"),
                    "original_sql": update.get("original_sql"),
                    "columns": update.get("columns", []),
                    "rows": rows[:row_limit],
                    "total_rows": update.get("total_rows", len(rows)),
                    "row_limit": row_limit,
                    "error": update.get("error"),
                    "review": update.get("review"),
                }
                if not update.get("error"):
                    yield {"type": "status", "text": "Explaining the result"}

    yield {"type": "done", "answer": final.get("answer", "")}


if __name__ == "__main__":
    import sys
    out = chat(sys.argv[1], " ".join(sys.argv[2:]))
    print("Intent:", out.get("route_info"))
    if out.get("sql"):
        print("SQL:\n", out["sql"])
    print("\nAnswer:", out["answer"])