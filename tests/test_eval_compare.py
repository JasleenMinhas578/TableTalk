from datetime import date

from evals.compare import results_match


def test_same_rows_in_any_order_match():
    assert results_match([("Delhi", 3), ("Pune", 1)], [("Pune", 1), ("Delhi", 3)])[0]


def test_column_names_and_order_do_not_matter():
    # expected (city, count) vs AI (count, city)
    assert results_match([("Delhi", 3), ("Pune", 1)], [(3, "Delhi"), (1, "Pune")])[0]


def test_extra_columns_from_the_ai_are_fine():
    assert results_match([("Olivia",)], [(17, "Olivia")])[0]


def test_numbers_are_rounded():
    assert results_match([(70.333333,)], [(70.33,)])[0]
    assert results_match([(4,)], [(4.0,)])[0]


def test_dates_compare_as_text():
    assert results_match([(date(2026, 1, 3),)], [(date(2026, 1, 3),)])[0]


def test_different_row_count_fails():
    ok, reason = results_match([(1,), (2,)], [(1,)])
    assert not ok and "rows" in reason


def test_different_values_fail():
    assert not results_match([("Delhi", 3)], [("Delhi", 4)])[0]


def test_missing_column_fails():
    assert not results_match([("Delhi", 3)], [("Delhi",)])[0]


def test_one_ai_column_cannot_match_two_expected_columns():
    assert not results_match([(1, 1)], [(1,)])[0]


def test_empty_results_match():
    assert results_match([], [])[0]
