from mirrsearch.docket_id import normalize_docket_id, looks_like_docket_id
from mirrsearch.internal_logic import _mark_exact_id_match, InternalLogic


# ---- regulations.gov family ----

def test_three_segment_id():
    assert normalize_docket_id("FAA-2026-0534") == "FAA-2026-0534"
    assert normalize_docket_id("USCG-2025-0091") == "USCG-2025-0091"


def test_four_segment_office_id():
    assert normalize_docket_id("DOT-OST-2023-0145") == "DOT-OST-2023-0145"


def test_four_segment_fda_letter_id():
    assert normalize_docket_id("FDA-2024-N-0019") == "FDA-2024-N-0019"


def test_five_segment_epa_id():
    assert normalize_docket_id("EPA-HQ-OPP-2009-0634") == "EPA-HQ-OPP-2009-0634"
    assert normalize_docket_id("EPA-R09-OAR-2023-0421") == "EPA-R09-OAR-2023-0421"


# ---- CMS-9115-F agency rule-code family ----

def test_cms_rule_code_with_stage():
    assert normalize_docket_id("CMS-9115-F") == "CMS-9115-F"
    assert normalize_docket_id("CMS-9115-P") == "CMS-9115-P"
    assert normalize_docket_id("CMS-9115-IFC") == "CMS-9115-IFC"


def test_cms_rule_code_without_stage():
    assert normalize_docket_id("CMS-9115") == "CMS-9115"


# ---- variant inputs canonicalize ----

def test_lowercase_canonicalizes():
    assert normalize_docket_id("cms-9115-f") == "CMS-9115-F"
    assert normalize_docket_id("faa-2026-0534") == "FAA-2026-0534"


def test_whitespace_separator_canonicalizes():
    assert normalize_docket_id("CMS 9115 F") == "CMS-9115-F"
    assert normalize_docket_id("FAA 2026 0534") == "FAA-2026-0534"


def test_mixed_separators_canonicalize():
    assert normalize_docket_id("CMS_9115-F") == "CMS-9115-F"
    assert normalize_docket_id("  cms 9115\tf ") == "CMS-9115-F"


# ---- non-docket queries return None ----

def test_plain_word_is_not_a_docket_id():
    assert normalize_docket_id("ESRD") is None
    assert normalize_docket_id("medicare") is None


def test_empty_or_whitespace_returns_none():
    assert normalize_docket_id("") is None
    assert normalize_docket_id(None) is None
    assert normalize_docket_id("   ") is None


def test_rule_code_without_real_year_is_not_treated_as_regulations_gov():
    # 9115 is not a YYYY year, so this is parsed as a rule code.
    assert normalize_docket_id("CMS-9115-F") == "CMS-9115-F"
    # Bare "AGENCY-NUMBER" with a non-year number is still recognized as a rule code.
    assert normalize_docket_id("CMS-1830") == "CMS-1830"


def test_garbage_returns_none():
    assert normalize_docket_id("CMS--") is None
    assert normalize_docket_id("---") is None
    assert normalize_docket_id("CMS-9115-ZZZ") is None  # ZZZ isn't a known stage
    assert normalize_docket_id("123-2024-0001") is None  # agency must be alpha


def test_looks_like_docket_id_predicate():
    assert looks_like_docket_id("CMS-9115-F") is True
    assert looks_like_docket_id("ESRD") is False


# ---- _mark_exact_id_match honors canonical form ----

def test_exact_match_marks_canonical_variant():
    result = {"results": [
        {"docket_id": "CMS-9115-F"},
        {"docket_id": "CMS-2018-0139"},
    ]}
    _mark_exact_id_match(result, "cms 9115 f")
    assert result["results"][0].get("isExactMatch") is True
    assert "isExactMatch" not in result["results"][1]


def test_exact_match_still_works_for_literal_query():
    result = {"results": [{"docket_id": "CMS-2025-0240"}]}
    _mark_exact_id_match(result, "CMS-2025-0240")
    assert result["results"][0]["isExactMatch"] is True


def test_exact_match_does_not_set_flag_for_unrelated_query():
    result = {"results": [{"docket_id": "CMS-2025-0240"}]}
    _mark_exact_id_match(result, "ESRD")
    assert "isExactMatch" not in result["results"][0]


# ---- AOSS is skipped when query is a docket id ----

def test_search_skips_aoss_for_docket_id_query():
    """Docket-ID queries shouldn't fan out into broad AOSS aggregations."""
    class StubDB:
        def __init__(self):
            self.text_match_called = False

        def search(self, *_a, **_kw):
            return []

        def text_match_terms(self, *_a, **_kw):
            self.text_match_called = True
            return []

        def get_dockets_by_ids(self, *_a, **_kw):
            return []

        def get_docket_document_comment_totals(self, *_a, **_kw):
            return {}

    stub = StubDB()
    InternalLogic("db", db_layer=stub).search("EPA-HQ-OPP-2009-0634")
    assert stub.text_match_called is False


def test_search_passes_canonical_id_as_exact_docket_id():
    """Rule-code queries need to flow through to db.search so the FR-side lookup fires."""
    captured = {}

    class StubDB:
        def search(self, *_a, **kw):
            captured.update(kw)
            return []

        def text_match_terms(self, *_a, **_kw):
            return []

        def get_dockets_by_ids(self, *_a, **_kw):
            return []

        def get_docket_document_comment_totals(self, *_a, **_kw):
            return {}

    InternalLogic("db", db_layer=StubDB()).search("cms 1849 p")
    assert captured.get("exact_docket_id") == "CMS-1849-P"


def test_search_does_not_pass_exact_docket_id_for_freetext():
    captured = {}

    class StubDB:
        def search(self, *_a, **kw):
            captured.update(kw)
            return []

        def text_match_terms(self, *_a, **_kw):
            return []

        def get_dockets_by_ids(self, *_a, **_kw):
            return []

        def get_docket_document_comment_totals(self, *_a, **_kw):
            return {}

    InternalLogic("db", db_layer=StubDB()).search("medicare")
    assert captured.get("exact_docket_id") is None


def test_search_still_calls_aoss_for_freetext_query():
    class StubDB:
        def __init__(self):
            self.text_match_called = False

        def search(self, *_a, **_kw):
            return []

        def text_match_terms(self, *_a, **_kw):
            self.text_match_called = True
            return []

        def get_dockets_by_ids(self, *_a, **_kw):
            return []

        def get_docket_document_comment_totals(self, *_a, **_kw):
            return {}

    stub = StubDB()
    InternalLogic("db", db_layer=stub).search("medicare")
    assert stub.text_match_called is True
