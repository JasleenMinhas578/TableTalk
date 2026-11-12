import pandas as pd
import pytest

import os
import time

from app.ingest import TooManyTables, clean_name, cleanup_old_sessions, ingest_files, unique_names


def test_clean_name():
    assert clean_name("Customer ID") == "customer_id"
    assert clean_name("2025 Sales!") == "_2025_sales"
    assert clean_name("   ") == "col"


def test_unique_names_handles_duplicates():
    assert unique_names(["Name", "name", "NAME "]) == ["name", "name_2", "name_3"]


def test_ingest_creates_one_table_per_sheet(data_dir, shop_xlsx):
    result = ingest_files([shop_xlsx])
    tables = {t["table"]: t for t in result["tables"]}
    assert set(tables) == {"shop_customers", "shop_products", "shop_orders"}
    assert tables["shop_orders"]["rows"] == 4
    assert "customer_id" in tables["shop_orders"]["columns"]
    assert result["reused"] is False


def test_same_upload_reuses_session(data_dir, shop_xlsx):
    first = ingest_files([shop_xlsx])
    second = ingest_files([shop_xlsx])
    assert second["session_id"] == first["session_id"]
    assert second["reused"] is True
    assert len(list(data_dir.glob("*.duckdb"))) == 1


def test_csv_supported(data_dir, tmp_path):
    path = tmp_path / "people.csv"
    pd.DataFrame({"id": [1, 2], "city": ["Delhi", "Pune"]}).to_csv(path, index=False)
    result = ingest_files([path])
    assert result["tables"][0]["table"] == "people"


def test_too_many_tables_rejected_and_nothing_saved(data_dir, tmp_path):
    path = tmp_path / "big.xlsx"
    with pd.ExcelWriter(path) as w:
        for i in range(6):
            pd.DataFrame({"x": [i]}).to_excel(w, sheet_name=f"S{i}", index=False)
    with pytest.raises(TooManyTables):
        ingest_files([path])
    assert list(data_dir.glob("*.duckdb")) == []


def test_empty_file_rejected(data_dir, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("a,b\n")
    with pytest.raises(ValueError):
        ingest_files([path])


def test_old_sessions_are_cleaned_up(tmp_path):
    old, new = tmp_path / "old.duckdb", tmp_path / "new.duckdb"
    old.write_text("x")
    new.write_text("x")
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    assert cleanup_old_sessions(days=7, folder=tmp_path) == 1
    assert not old.exists() and new.exists()
    assert cleanup_old_sessions(days=0, folder=tmp_path) == 0     # 0 = keep forever
