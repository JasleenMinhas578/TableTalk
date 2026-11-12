"""Tests for the rephrase safety check (no model needed)."""

from app.agent.rephrase import key_details, missing_details


def test_key_details_finds_numbers_names_and_quotes():
    assert key_details('Which 5 customers in Mumbai spent the most in 2025?') == {"5", "mumbai", "2025"}
    assert key_details('orders with status "Pending"') == {"pending"}


def test_first_word_and_acronyms_are_not_details():
    assert key_details("Show me SQL for sales") == set()


def test_rewrite_that_keeps_everything_passes():
    assert missing_details("Which 5 customers in Mumbai spent the most?",
                           "Top 5 customers in the city Mumbai by total spend") == []


def test_rewrite_that_changes_a_number_is_caught():
    assert missing_details("Which 5 customers spent the most?", "Top 10 customers by spend") == ["5"]


def test_number_inside_another_number_does_not_count():
    assert missing_details("Top 5 products", "Top products in 2025") == ["5"]


def test_dropped_name_is_caught():
    assert missing_details("Orders from Delhi last month", "Orders from last month") == ["delhi"]
