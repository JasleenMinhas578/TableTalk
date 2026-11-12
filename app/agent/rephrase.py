"""Rephrase a vague question into a clearer one, using the user's real table and column names.

How it works:
  1. Skip it when rephrasing can't help: pasted SQL, small talk, off-topic messages.
  2. Ask the small model (Llama 3.2 3B, JSON mode) for one clearer question, giving it the
     schema so it can use real names ("sales" -> "the amount column in transactions").
  3. If the question is too vague to rewrite safely, the model asks a clarifying question instead.
  4. Check the rewrite kept every detail from the original (numbers, names like "Mumbai",
     quoted words). If anything was dropped, the rewrite is rejected rather than shown.

The user always sees the suggestion first and chooses "Use this"; nothing is replaced silently.
"""

import json
import re

from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler

from app.agent.router import route, schema_summary
from app.agent.sql_agent import SMALL_MODEL, split_sql_and_question

rewriter = ChatOllama(model=SMALL_MODEL, temperature=0, format="json")

NUMBER = re.compile(r"\d+(?:\.\d+)?")
QUOTED = re.compile(r"[\"']([^\"']+)[\"']")


def key_details(text: str) -> set[str]:
    """Things a rewrite must keep: numbers, quoted text, and capitalised names (not the first word)."""
    details = set(NUMBER.findall(text))
    details |= {q.strip().lower() for q in QUOTED.findall(text)}
    words = re.findall(r"[A-Za-z][\w-]*", text)
    details |= {w.lower() for w in words[1:] if w[0].isupper() and not w.isupper()}
    return details


def missing_details(original: str, rewrite: str) -> list[str]:
    """Details from the original that the rewrite dropped."""
    lowered = rewrite.lower()
    # Whole-word match, so "5" isn't found inside "2025"
    return sorted(
        d for d in key_details(original)
        if not re.search(rf"(?<![\w.]){re.escape(d.lower())}(?![\w]|\.\d)", lowered)
    )


def rephrase(message: str, schema: dict) -> dict:
    """Return {"rephrased": str|None, "clarify": str|None, "reason": str|None}."""
    message = message.strip()
    none = {"rephrased": None, "clarify": None, "reason": None}

    sql, _ = split_sql_and_question(message)
    if sql:
        return {**none, "reason": "That looks like SQL. Use \"Fix my SQL\" in the playground to check it."}

    intent = route(message, schema)["intent"]
    if intent == "small_talk":
        return {**none, "reason": "There's no data question to rephrase. Ask something about your tables."}
    if intent == "off_topic":
        return {**none, "reason": "That isn't about your data, so there's nothing to rephrase."}

    prompt = (
        "Rewrite the user's question about their data so it is clear and specific.\n"
        f"Their tables and columns: {schema_summary(schema)}\n\n"
        "Rules:\n"
        "- Use the real table and column names where they make the question clearer.\n"
        "- Keep every number, name, date and filter from the original. Never add new filters.\n"
        "- Keep relative dates like 'last month' as they are; do not invent exact dates.\n"
        "- Keep it to one question, in plain English.\n"
        "- If you truly cannot tell what they want, ask one short clarifying question instead.\n\n"
        f"Question: {message}\n"
        'Reply in JSON: {"rephrased": "the clearer question, or null", '
        '"clarify": "a clarifying question, or null"}'
    )
    try:
        reply = rewriter.invoke(prompt, config={"callbacks": [CallbackHandler()]})
        out = json.loads(reply.content)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {**none, "reason": "Couldn't rephrase that right now. Try again, or send it as it is."}

    rephrased = (out.get("rephrased") or "").strip() or None
    clarify = (out.get("clarify") or "").strip() or None

    if rephrased:
        dropped = missing_details(message, rephrased)
        if dropped:
            # Safer to show nothing than a rewrite that quietly changed the question
            return {**none, "reason": f"The rewrite dropped {', '.join(dropped)}, so I left your question as it is."}
        if rephrased.lower().rstrip("?. ") == message.lower().rstrip("?. "):
            return {**none, "reason": "Your question is already clear."}
        return {**none, "rephrased": rephrased}

    if clarify:
        return {**none, "clarify": clarify}
    return {**none, "reason": "Couldn't find a clearer way to say that."}
