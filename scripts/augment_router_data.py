import csv
import json
from pathlib import Path

from langchain_ollama import ChatOllama

llm = ChatOllama(model="qwen2.5-coder:7b", temperature=0.8, format="json")
src = Path("training/router_examples.csv")
out = Path("training/router_augmented.csv")

with src.open() as f:
    rows = [(r["text"], r["intent"]) for r in csv.DictReader(f)]

# Resume support: skip sources already done, avoid duplicates
done, seen = set(), {t.lower() for t, _ in rows}
if out.exists():
    with out.open() as f:
        for r in csv.DictReader(f):
            done.add(r["source"])
            seen.add(r["text"].lower())
else:
    with out.open("w", newline="") as f:
        csv.writer(f).writerow(["text", "intent", "source"])

todo = [(t, i) for t, i in rows if t not in done]
print(f"{len(done)} already done, {len(todo)} to go")

added = 0
for n, (text, intent) in enumerate(todo, 1):
    prompt = (
        f"Rewrite this message 5 different ways a real user might type it. "
        f"Keep the same meaning and intent ({intent}). Vary wording, length and tone; "
        f"include casual phrasing and small typos.\n"
        f"Message: {text}\n"
        'Reply in JSON: {"rewrites": ["...", "...", "...", "...", "..."]}'
    )
    try:
        rewrites = json.loads(llm.invoke(prompt).content).get("rewrites", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        rewrites = []

    new = []
    for r in rewrites:
        r = str(r).strip()
        if r and r.lower() not in seen:
            seen.add(r.lower())
            new.append((r, intent, text))
    # Save after every example, so nothing is lost if you stop it
    with out.open("a", newline="") as f:
        csv.writer(f).writerows(new or [("", intent, text)])
    added += len(new)
    print(f"[{n}/{len(todo)}] +{len(new)}  ({intent}) {text[:50]}")

print(f"Done. Added {added} examples to {out}")