import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(*paths):
    files = [("files", (Path(p).name, Path(p).read_bytes(), XLSX)) for p in paths]
    return client.post("/upload", files=files)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_then_schema(data_dir, shop_xlsx):
    r = upload(shop_xlsx)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert len(r.json()["tables"]) == 3

    schema = client.get(f"/schema/{sid}").json()
    assert len(schema["relationships"]) == 2


def test_unsupported_file_rejected(data_dir, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    r = client.post("/upload", files=[("files", ("notes.txt", bad.read_bytes(), "text/plain"))])
    assert r.status_code == 400


def test_too_many_files_rejected(data_dir, shop_xlsx):
    assert upload(*[shop_xlsx] * 6).status_code == 400


def test_bad_session_ids(data_dir):
    assert client.get("/schema/../../etc").status_code in (400, 404)
    assert client.get("/schema/not-a-real-id").status_code == 400
    assert client.get("/schema/" + "a" * 32).status_code == 404


def test_run_sql_works_and_blocks(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]

    ok = client.post("/run-sql", json={"session_id": sid,
                                       "sql": "SELECT COUNT(*) AS n FROM shop_orders"})
    assert ok.status_code == 200
    assert ok.json()["rows"] == [[4]]

    bad = client.post("/run-sql", json={"session_id": sid, "sql": "DELETE FROM shop_orders"})
    assert bad.status_code == 400


def test_empty_chat_message_rejected(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]
    assert client.post("/chat", json={"session_id": sid, "message": "  "}).status_code == 400


# ---------- slow end-to-end test, only when asked ----------

@pytest.mark.ollama
@pytest.mark.skipif(os.getenv("RUN_OLLAMA_TESTS") != "1", reason="needs Ollama")
def test_chat_off_topic_refused(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]
    r = client.post("/chat", json={"session_id": sid, "message": "what's the weather today?"})
    assert r.status_code == 200
    assert r.json()["intent"] == "off_topic"


def test_samples_listed():
    ids = {s["id"] for s in client.get("/samples").json()}
    assert ids == {"shop", "fraud", "school"}


@pytest.mark.parametrize("sample_id", ["shop", "fraud", "school"])
def test_each_sample_loads_with_links(data_dir, sample_id):
    first = client.post(f"/samples/{sample_id}")
    assert first.status_code == 200, first.text
    assert len(first.json()["tables"]) == 3
    sid = first.json()["session_id"]
    assert len(client.get(f"/schema/{sid}").json()["relationships"]) == 2

    again = client.post(f"/samples/{sample_id}")
    assert again.json()["session_id"] == sid
    assert again.json()["reused"] is True


def test_unknown_sample_rejected(data_dir):
    assert client.post("/samples/nope").status_code == 404


def test_big_results_are_capped_but_counted(data_dir):
    sid = client.post("/samples/fraud").json()["session_id"]
    r = client.post("/run-sql", json={"session_id": sid, "sql": "SELECT * FROM bank_fraud_transactions"})
    body = r.json()
    assert r.status_code == 200
    assert len(body["rows"]) == body["row_limit"] == 100
    assert body["total_rows"] == 300


def test_generate_sql_needs_a_question(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]
    r = client.post("/generate-sql", json={"session_id": sid, "question": "   "})
    assert r.status_code == 400


def test_stream_rejects_empty_message(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]
    assert client.post("/chat/stream", json={"session_id": sid, "message": " "}).status_code == 400


def test_test_cases_save_list_and_delete(data_dir):
    sid = client.post("/samples/shop").json()["session_id"]
    bad = client.post("/test-cases", json={"session_id": sid, "question": "x", "sql": "DELETE FROM shop_data_orders"})
    assert bad.status_code == 400
    no_q = client.post("/test-cases", json={"session_id": sid, "question": " ", "sql": "SELECT 1"})
    assert no_q.status_code == 400

    case = client.post("/test-cases", json={"session_id": sid, "question": "How many orders?",
                                            "sql": "SELECT COUNT(*) FROM shop_data_orders"}).json()
    assert case["dataset"] == "shop"          # samples are stored by name, so evals work anywhere
    assert [c["id"] for c in client.get(f"/test-cases/{sid}").json()] == [case["id"]]
    assert client.delete(f"/test-cases/{case['id']}").status_code == 200
    assert client.get(f"/test-cases/{sid}").json() == []


def test_rephrase_rejects_empty_message(data_dir, shop_xlsx):
    sid = upload(shop_xlsx).json()["session_id"]
    assert client.post("/rephrase", json={"session_id": sid, "message": "  "}).status_code == 400
