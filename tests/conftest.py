import pandas as pd
import pytest

import app.eval_cases as eval_cases
import app.ingest as ingest
import app.main as main


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point every session database at a temp folder, never data/sessions."""
    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(ingest, "DATA_DIR", d)
    monkeypatch.setattr(main, "DATA_DIR", d)
    monkeypatch.setattr(eval_cases, "CASES_FILE", tmp_path / "sql_cases.jsonl")
    return d


@pytest.fixture
def shop_xlsx(tmp_path):
    """A small Excel file with 3 linked sheets and a known right answer."""
    customers = pd.DataFrame({"Customer ID": [1, 2, 3], "Name": ["A", "B", "C"]})
    products = pd.DataFrame({"Product ID": [10, 20], "Product Name": ["Pen", "Cup"]})
    orders = pd.DataFrame({
        "Order ID": [100, 101, 102, 103],
        "Customer ID": [1, 2, 2, 3],
        "Product ID": [10, 20, 10, 10],
        "Quantity": [1, 2, 3, 4],
        "Status": ["Done", "Done", "Pending", "Done"],
    })
    path = tmp_path / "shop.xlsx"
    with pd.ExcelWriter(path) as w:
        customers.to_excel(w, sheet_name="Customers", index=False)
        products.to_excel(w, sheet_name="Products", index=False)
        orders.to_excel(w, sheet_name="Orders", index=False)
    return path


@pytest.fixture
def shop_db(data_dir, shop_xlsx):
    """The sample file already loaded into DuckDB."""
    return ingest.ingest_files([shop_xlsx])["db_path"]
