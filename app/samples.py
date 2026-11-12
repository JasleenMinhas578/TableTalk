"""The sample datasets people can try without uploading anything.

The Excel files are created by: uv run python -m scripts.make_sample_datasets
"""

from pathlib import Path

SAMPLES_DIR = Path("samples")

SAMPLES = {
    "shop": {
        "file": "shop_data.xlsx",
        "title": "Online shop",
        "description": "30 customers, 10 products and 100 orders.",
        "try_asking": "Which 5 customers spent the most?",
    },
    "fraud": {
        "file": "bank_fraud.xlsx",
        "title": "Bank card fraud",
        "description": "40 accounts, 12 merchants and 300 card transactions, some flagged as fraud.",
        "try_asking": "Which merchant categories have the most fraud?",
    },
    "school": {
        "file": "school_data.xlsx",
        "title": "School results",
        "description": "40 students, 8 courses and 160 enrollments with scores and attendance.",
        "try_asking": "Average score per course",
    },
}


def sample_path(sample_id: str) -> Path | None:
    info = SAMPLES.get(sample_id)
    return SAMPLES_DIR / info["file"] if info else None


def list_samples() -> list[dict]:
    return [
        {"id": sid, **{k: v for k, v in info.items() if k != "file"},
         "available": (SAMPLES_DIR / info["file"]).exists()}
        for sid, info in SAMPLES.items()
    ]
