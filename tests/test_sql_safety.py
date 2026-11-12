import pytest

from app.agent.sql_agent import check_sql, run_sql, split_sql_and_question

TABLES = ["shop_customers", "shop_products", "shop_orders"]


def state(sql, db_path="unused"):
    return {"sql": sql, "tables": TABLES, "retries": 0, "db_path": db_path}


# ---------- check_sql: what's allowed ----------

@pytest.mark.parametrize("sql", [
    "SELECT * FROM shop_orders",
    "SELECT c.name, SUM(o.quantity) FROM shop_orders o "
    "JOIN shop_customers c ON o.customer_id = c.customer_id GROUP BY 1",
    "WITH big AS (SELECT * FROM shop_orders WHERE quantity > 2) SELECT COUNT(*) FROM big",
])
def test_safe_queries_pass(sql):
    assert check_sql(state(sql))["error"] is None


# ---------- check_sql: what's blocked ----------

@pytest.mark.parametrize("sql, reason", [
    ("DELETE FROM shop_orders", "read-only"),
    ("DROP TABLE shop_orders", "read-only"),
    ("UPDATE shop_orders SET quantity = 0", "read-only"),
    ("SELECT 1; DROP TABLE shop_orders", "one statement"),
    ("SELECT * FROM read_csv('/etc/passwd')", "file"),
    ("SELECT * FROM secret_table", "unknown table"),
])
def test_unsafe_queries_blocked(sql, reason):
    out = check_sql(state(sql))
    assert out["error"], f"should block ({reason}): {sql}"
    assert out["retries"] == 1


def test_syntax_error_caught():
    assert check_sql(state("SELECT name FROM shop_customers WHERE"))["error"]


# ---------- run_sql ----------

def test_run_sql_returns_rows(shop_db):
    out = run_sql(state("SELECT COUNT(*) AS n FROM shop_orders", shop_db))
    assert out["error"] is None
    assert out["columns"] == ["n"]
    assert out["rows"] == [[4]]


def test_run_sql_reports_bad_column(shop_db):
    out = run_sql(state("SELECT nope FROM shop_orders", shop_db))
    assert out["error"]


# ---------- split_sql_and_question (rule paths only) ----------

def test_plain_question_has_no_sql():
    assert split_sql_and_question("which customers spent the most") == \
        (None, "which customers spent the most")


def test_english_select_is_not_sql():
    sql, _ = split_sql_and_question("Select the best customers")
    assert sql is None


def test_pure_sql():
    sql, q = split_sql_and_question("SELECT name FROM shop_customers")
    assert sql == "SELECT name FROM shop_customers"
    assert q == ""


def test_sql_then_question_on_new_line():
    sql, q = split_sql_and_question("SELECT status FROM shop_orders\nis this right?")
    assert sql == "SELECT status FROM shop_orders"
    assert q == "is this right?"


def test_sql_then_question_after_semicolon():
    sql, q = split_sql_and_question("SELECT status FROM shop_orders; is this right?")
    assert sql == "SELECT status FROM shop_orders"
    assert q == "is this right?"
