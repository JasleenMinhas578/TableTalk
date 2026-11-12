import csv
import json
import random
import re
from pathlib import Path

import joblib
import numpy as np
from langchain_ollama import ChatOllama, OllamaEmbeddings
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

from app.agent.sql_agent import split_sql_and_question

# ---------- settings ----------

INTENTS = ["sql", "dataset", "small_talk", "off_topic"]
MODEL_PATH = Path("models/router.joblib")
BASE_CSV = Path("training/router_examples.csv")
AUG_CSV = Path("training/router_augmented.csv")
HARD_CSV = Path("training/router_hard.csv")     # hand-written boundary cases
THRESHOLD = 0.8

embedder = OllamaEmbeddings(model="nomic-embed-text")
fallback_llm = ChatOllama(model="llama3.2:3b", temperature=0, format="json")

SMALL_TALK = re.compile(
    r"^\s*(hi+|hello|hey|thanks|thank you|ok|okay|cool|bye|cheers|"
    r"good (morning|afternoon|evening))\b[\s!.,a-z]{0,20}$", re.I)
DATA_WORDS = re.compile(
    r"\b(total|average|avg|sum|count|how many|top \d+|highest|lowest|max|min|"
    r"per|group|by month|trend|list|show me)\b", re.I)
GENERIC_NAMES = {"data", "id", "shop", "name", "date", "type"}


def embed(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed in small batches; one huge request can crash Ollama's embed server."""
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = [f"classification: {t}" for t in texts[i:i + batch_size]]
        vectors.extend(embedder.embed_documents(batch))
    return np.array(vectors)


def schema_words(schema: dict) -> set[str]:
    """Words from table and column names, used by the rules layer."""
    names = set()
    for t, info in schema.get("tables", {}).items():
        names.update(t.lower().split("_"))
        for c in info["columns"]:
            names.update(c["name"].lower().split("_"))
    return names - GENERIC_NAMES


def schema_summary(schema: dict) -> str:
    return ", ".join(
        f"{t} ({', '.join(c['name'] for c in info['columns'])})"
        for t, info in schema.get("tables", {}).items()
    ) or "none uploaded"


# ---------- layer 1: rules ----------

def rule_layer(message: str, names: set[str]) -> str | None:
    if SMALL_TALK.match(message):
        return "small_talk"
    sql, _ = split_sql_and_question(message)
    if sql:
        return "sql"                                   # pasted SQL
    words = set(re.findall(r"[a-z_]+", message.lower()))
    if DATA_WORDS.search(message) and words & names:
        return "sql"                                   # data word + real column/table
    return None


# ---------- layer 2: classifier ----------

_clf = None


def load_classifier():
    global _clf
    if _clf is None and MODEL_PATH.exists():
        _clf = joblib.load(MODEL_PATH)
    return _clf


def classifier_layer(message: str) -> tuple[str | None, float]:
    clf = load_classifier()
    if clf is None:
        return None, 0.0
    probs = clf.predict_proba(embed([message]))[0]
    best = int(np.argmax(probs))
    return str(clf.classes_[best]), float(probs[best])


# ---------- layer 3: LLM fallback ----------

def llm_layer(message: str, summary: str) -> str:
    prompt = (
        "Classify the user's message for a data assistant that only answers questions "
        "about the user's uploaded tables.\n"
        f"Tables: {summary}\n\n"
        "Intents:\n"
        "- sql: asks for numbers, lists or analysis from the data\n"
        "- dataset: asks what tables or columns exist or what they mean\n"
        "- small_talk: greetings, thanks, questions about the assistant\n"
        "- off_topic: anything unrelated to the data\n\n"
        f"Message: {message}\n"
        'Reply in JSON: {"intent": "sql" | "dataset" | "small_talk" | "off_topic"}'
    )
    try:
        intent = json.loads(fallback_llm.invoke(prompt).content).get("intent")
        return intent if intent in INTENTS else "off_topic"
    except (json.JSONDecodeError, TypeError, AttributeError):
        return "off_topic"                             # safe default


# ---------- main entry ----------

def route(message: str, schema: dict | None = None) -> dict:
    """Return {"intent", "layer", "confidence"}."""
    schema = schema or {"tables": {}}

    intent = rule_layer(message, schema_words(schema))
    if intent:
        return {"intent": intent, "layer": "rules", "confidence": 1.0}

    intent, conf = classifier_layer(message)
    if intent and conf >= THRESHOLD:
        return {"intent": intent, "layer": "classifier", "confidence": round(conf, 3)}

    return {"intent": llm_layer(message, schema_summary(schema)),
            "layer": "llm", "confidence": round(conf, 3)}


# ---------- training ----------

EVAL_CSV = Path("training/router_golden_eval.csv")        # hand-written, never trained on
CACHE_PATH = Path("models/embedding_cache.joblib")


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [r for r in csv.DictReader(f) if r.get("text", "").strip()]


def embed_cached(texts: list[str]) -> np.ndarray:
    """Embed each sentence once and remember it, so retraining is fast."""
    cache = joblib.load(CACHE_PATH) if CACHE_PATH.exists() else {}
    missing = [t for t in dict.fromkeys(texts) if t not in cache]
    if missing:
        print(f"Embedding {len(missing)} new sentences...")
        for t, v in zip(missing, embed(missing)):
            cache[t] = v
        CACHE_PATH.parent.mkdir(exist_ok=True)
        joblib.dump(cache, CACHE_PATH)
    return np.array([cache[t] for t in texts])


def make_classifier(C: float = 1.0):
    # Higher C = less regularisation = sharper, more confident probabilities
    return LogisticRegression(C=C, max_iter=5000, class_weight="balanced")


def report(title: str, y_true, y_pred, texts: list[str]):
    print(f"\n===== {title} ({len(y_true)} examples) =====")
    print(classification_report(y_true, y_pred, labels=INTENTS, zero_division=0))
    print("Confusion matrix (rows = true, columns = predicted), order:", INTENTS)
    print(confusion_matrix(y_true, y_pred, labels=INTENTS))
    wrong = [(t, a, b) for t, a, b in zip(texts, y_true, y_pred) if a != b]
    if wrong:
        print(f"\nMistakes ({len(wrong)}):")
        for t, a, b in wrong[:40]:
            print(f"  [{a} -> {b}] {t}")


def train(folds: int = 5, seed: int = 42):
    base, aug = load_rows(BASE_CSV) + load_rows(HARD_CSV), load_rows(AUG_CSV)
    if not base:
        raise SystemExit(f"No examples found in {BASE_CSV}. Run make_router_data first.")

    # Each paraphrase is grouped with the sentence it came from
    rows = [dict(r, group=r["text"]) for r in base] + \
           [dict(r, group=r.get("source") or r["text"]) for r in aug]
    texts = [r["text"] for r in rows]
    y = np.array([r["intent"] for r in rows])
    groups = [r["group"] for r in rows]
    X = embed_cached(texts)

    # 1. Cross-validation: every example is tested exactly once,
    #    and paraphrases always stay in the same fold as their source (no leakage).
    #    We try several C values and keep the one with the best macro F1.
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    splits = list(cv.split(X, y, groups))
    best_C, best_f1, best_pred = None, -1.0, None
    print("\nTuning C (cross-validated macro F1):")
    for C in (0.5, 1, 4, 16, 64):
        pred = np.empty(len(rows), dtype=object)
        for train_idx, test_idx in splits:
            pred[test_idx] = make_classifier(C).fit(X[train_idx], y[train_idx]).predict(X[test_idx])
        f1 = f1_score(y, pred, average="macro")
        print(f"  C={C:<4} macro F1 = {f1:.3f}")
        if f1 > best_f1:
            best_C, best_f1, best_pred = C, f1, pred
    print(f"Best C = {best_C}")
    report(f"{folds}-fold cross-validation (C={best_C})", y, best_pred, texts)

    # 2. Final model: learn from every example
    clf = make_classifier(best_C).fit(X, y)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    global _clf
    _clf = clf
    print(f"\nSaved {MODEL_PATH}")

    # 3. Golden eval set: hand-written messages the model has never seen
    seen = {t.lower() for t in texts}
    gold = [r for r in load_rows(EVAL_CSV) if r["text"].lower() not in seen]
    if not gold:
        print(f"\n(No golden eval set at {EVAL_CSV}, skipping.)")
        return
    gx = embed_cached([r["text"] for r in gold])
    gy = [r["intent"] for r in gold]
    probs = clf.predict_proba(gx)
    gpred = clf.classes_[probs.argmax(axis=1)]
    report("Golden eval set (classifier only)", gy, gpred, [r["text"] for r in gold])

    # Threshold sweep: how many messages the classifier can decide alone, and how accurately
    right = gpred == np.array(gy)
    top = probs.max(axis=1)
    print("\nThreshold sweep on the golden set:")
    print("  threshold | decided by classifier | correct | accuracy | sent to LLM")
    for t in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        conf = top >= t
        n, ok = int(conf.sum()), int((right & conf).sum())
        acc = f"{ok / n:.0%}" if n else "-"
        print(f"  {t:>9} | {n:>21} | {ok:>7} | {acc:>8} | {int((~conf).sum()):>11}")
    print(f"(Current THRESHOLD = {THRESHOLD}. Pick the lowest one that still has ~100% accuracy.)")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["train"]:
        train()
    elif len(sys.argv) >= 3:
        from app.schema import get_schema
        print(route(" ".join(sys.argv[2:]), get_schema(sys.argv[1])))
    else:
        print("Usage:")
        print("  uv run python -m app.agent.router train")
        print('  uv run python -m app.agent.router <db_path> "<message>"')