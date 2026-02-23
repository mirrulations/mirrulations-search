"""
Tests for MockDBLayer — verifies that the mock's dummy data and search
behavior are correct. These are the tests that previously lived in
test_db.py but relied on DBLayer._items (which no longer exists).
"""
# pylint: disable=redefined-outer-name
import pytest
from mock_db import MockDBLayer


@pytest.fixture
def db():
    return MockDBLayer()


# --- _items ---

def test_items_returns_list(db):
    assert isinstance(db._items(), list)


def test_items_returns_two_records(db):
    assert len(db._items()) == 2


def test_items_have_required_fields(db):
    required_fields = ["docket_id", "title", "cfrPart", "agency_id", "document_type"]
    for item in db._items():
        for field in required_fields:
            assert field in item, f"Item missing required field: {field}"


def test_items_field_types(db):
    for item in db._items():
        assert isinstance(item["docket_id"], str)
        assert isinstance(item["title"], str)
        assert isinstance(item["cfrPart"], str)
        assert isinstance(item["agency_id"], str)
        assert isinstance(item["document_type"], str)


def test_items_content(db):
    items = db._items()
    assert items[0]["docket_id"] == "CMS-2025-0240"
    assert items[0]["agency_id"] == "CMS"
    assert items[0]["document_type"] == "Proposed Rule"
    assert items[1]["docket_id"] == "CMS-2025-0240"
    assert items[1]["agency_id"] == "CMS"


# --- search ---

def test_search_returns_list(db):
    assert isinstance(db.search("CMS"), list)


def test_search_finds_by_docket_id(db):
    result = db.search("CMS-2025-0240")
    assert len(result) == 2
    assert all(item["docket_id"] == "CMS-2025-0240" for item in result)


def test_search_finds_by_title(db):
    result = db.search("ESRD")
    assert len(result) >= 1
    assert all("ESRD" in item["title"] or "esrd" in item["title"].lower() for item in result)


def test_search_is_case_insensitive(db):
    result_upper = db.search("CMS")
    result_lower = db.search("cms")
    result_mixed = db.search("Cms")
    assert len(result_upper) == len(result_lower) == len(result_mixed)
    assert result_upper == result_lower == result_mixed


def test_search_strips_whitespace(db):
    assert db.search("CMS") == db.search("  CMS  ")


def test_search_partial_match_title(db):
    result = db.search("Medicare")
    assert len(result) >= 1
    assert any("Medicare" in item["title"] for item in result)


def test_search_partial_match_docket(db):
    result = db.search("2025")
    assert len(result) == 2


def test_search_no_results(db):
    result = db.search("nonexistent_query_xyz123")
    assert result == []


def test_search_empty_string_returns_all(db):
    assert len(db.search("")) == 2


def test_search_specific_terms(db):
    assert len(db.search("Prospective Payment System")) >= 1
    assert len(db.search("Quality Incentive")) >= 1


def test_search_multiple_words(db):
    assert len(db.search("End-Stage Renal")) >= 1


def test_search_returns_correct_structure(db):
    for item in db.search("CMS"):
        assert isinstance(item, dict)
        for field in ["docket_id", "title", "cfrPart", "agency_id", "document_type"]:
            assert field in item


def test_search_does_not_modify_original_data(db):
    original = db._items()
    db.search("CMS")
    db.search("Medicare")
    db.search("xyz")
    assert db._items() == original


def test_search_special_characters(db):
    assert len(db.search("CMS-2025")) == 2


def test_search_numbers_only(db):
    assert len(db.search("2025")) == 2


def test_search_with_parentheses(db):
    assert len(db.search("(ESRD)")) >= 1


# --- filter_param ---

def test_search_filter_matching_document_type(db):
    result = db.search("renal", "Proposed Rule")
    assert len(result) > 0
    assert all(item["document_type"] == "Proposed Rule" for item in result)


def test_search_filter_nonexistent_document_type(db):
    assert db.search("renal", "Final Rule") == []


def test_search_filter_is_case_insensitive(db):
    lower = db.search("renal", "proposed rule")
    upper = db.search("renal", "PROPOSED RULE")
    mixed = db.search("renal", "Proposed Rule")
    assert lower == upper == mixed
