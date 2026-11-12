import pandas as pd
import pytest

import app.ingest as ingest
from app.schema import get_schema


@pytest.fixture
def sample_db(tmp_path, monkeypatch):
    # Save test databases in a temporary folder, not data/sessions
    monkeypatch.setattr(ingest, "DATA_DIR", tmp_path)

    customers = pd.DataFrame({"Customer ID": [1, 2, 3], "Name": ["A", "B", "C"]})
    products = pd.DataFrame({"Product ID": [10, 20], "Product Name": ["Pen", "Cup"]})
    orders = pd.DataFrame({
        "Order ID": [100, 101, 102, 103],
        "Customer ID": [1, 2, 2, 3],
        "Product ID": [10, 20, 10, 10],
        "Status": ["Done", "Done", "Pending", "Done"],
    })

    path = tmp_path / "shop.xlsx"
    with pd.ExcelWriter(path) as w:
        customers.to_excel(w, sheet_name="Customers", index=False)
        products.to_excel(w, sheet_name="Products", index=False)
        orders.to_excel(w, sheet_name="Orders", index=False)

    return ingest.ingest_files([path])["db_path"]


def test_keys_detected(sample_db):
    tables = get_schema(sample_db)["tables"]
    keys = {
        t: [c["name"] for c in info["columns"] if c["is_key"]]
        for t, info in tables.items()
    }
    assert "customer_id" in keys["shop_customers"]
    assert "product_id" in keys["shop_products"]
    assert "order_id" in keys["shop_orders"]


def test_relationships_exact(sample_db):
    rels = get_schema(sample_db)["relationships"]
    found = {(r["from_table"], r["from_column"], r["to_table"], r["to_column"]) for r in rels}
    assert found == {
        ("shop_orders", "customer_id", "shop_customers", "customer_id"),
        ("shop_orders", "product_id", "shop_products", "product_id"),
    }