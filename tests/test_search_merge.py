# pylint: disable=too-few-public-methods,unused-argument
"""Tests for OpenSearch merge path in InternalLogic.search()."""
from datetime import date

from mirrsearch.internal_logic import InternalLogic


class _FakeDbMerge:
    def __init__(self, sql_rows, os_hits, by_id_rows):
        self._sql_rows = sql_rows
        self._os_hits = os_hits
        self._by_id_rows = by_id_rows
        self.get_dockets_by_ids_calls = []

    def search(self, query, *args, **kwargs):  # pylint: disable=unused-argument
        return list(self._sql_rows)

    def text_match_terms(self, terms, opensearch_client=None):
        return list(self._os_hits)

    def get_dockets_by_ids(self, docket_ids):
        self.get_dockets_by_ids_calls.append(list(docket_ids))
        return list(self._by_id_rows)

    def get_dockets_by_ids_filtered(  # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
            self, docket_ids, docket_type_param=None,
            agency=None, cfr_part_param=None,
            start_date=None, end_date=None):
        self.get_dockets_by_ids_calls.append(list(docket_ids))
        return list(self._by_id_rows)

    def get_docket_document_comment_totals(self, docket_ids, opensearch_client=None):  # pylint: disable=unused-argument
        dids = [str(d) for d in docket_ids]
        totals = {
            "A": {"document_total_count": 10, "comment_total_count": 2},
            "B": {"document_total_count": 4, "comment_total_count": 5},
            "C": {"document_total_count": 7, "comment_total_count": 3},
        }
        return {d: totals[d] for d in dids if d in totals}

def test_search_json_sanitizes_modify_date():
    """Postgres-style date objects become ISO strings for JSON responses."""
    sql_rows = [
        {
            "docket_id": "A",
            "docket_title": "t",
            "cfr_refs": [],
            "modify_date": date(2024, 6, 15),
        },
    ]
    db = _FakeDbMerge(sql_rows, os_hits=[], by_id_rows=[])
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    assert out["results"][0]["modify_date"] == "2024-06-15"


def test_merge_opensearch_empty_uses_sql_only_with_match_source():
    db = _FakeDbMerge(
        sql_rows=[{"docket_id": "A", "docket_title": "t", "cfr_refs": []}],
        os_hits=[],
        by_id_rows=[],
    )
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    assert len(out["results"]) == 1
    assert out["results"][0]["match_source"] == "title"
    assert out["results"][0]["documentNumerator"] == 0
    assert out["results"][0]["commentNumerator"] == 0
    assert out["results"][0]["documentDenominator"] == 10
    assert out["results"][0]["commentDenominator"] == 2
    assert not db.get_dockets_by_ids_calls



def test_merge_appends_full_text_with_counts_and_order():  # pylint: disable=too-many-statements
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": []}]
    os_hits = [
        {"docket_id": "A", "document_match_count": 9, "comment_match_count": 1},
        {"docket_id": "B", "document_match_count": 2, "comment_match_count": 3},
        {"docket_id": "C", "document_match_count": 1, "comment_match_count": 0},
    ]
    by_id_rows = [
        {"docket_id": "C", "docket_title": "tc", "cfr_refs": []},
        {"docket_id": "B", "docket_title": "tb", "cfr_refs": []},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    merged = out["results"]
    assert [r["docket_id"] for r in merged] == ["A", "B", "C"]
    assert merged[0]["match_source"] == "title"
    assert merged[0]["documentNumerator"] == 9
    assert merged[0]["commentNumerator"] == 1
    assert merged[0]["documentDenominator"] == 10
    assert merged[0]["commentDenominator"] == 2
    assert merged[1]["match_source"] == "full_text"
    assert merged[1]["documentNumerator"] == 2
    assert merged[1]["commentNumerator"] == 3
    assert merged[1]["documentDenominator"] == 4
    assert merged[1]["commentDenominator"] == 5
    assert merged[2]["match_source"] == "full_text"
    assert merged[2]["documentNumerator"] == 1
    assert merged[2]["documentDenominator"] == 7
    assert db.get_dockets_by_ids_calls == [["B", "C"]]


def test_merge_skips_os_docket_missing_in_postgres():
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": []}]
    os_hits = [{"docket_id": "B", "document_match_count": 1, "comment_match_count": 0}]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows=[])
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    assert len(out["results"]) == 1
    assert out["results"][0]["docket_id"] == "A"
    assert out["results"][0]["documentNumerator"] == 0
    assert out["results"][0]["commentNumerator"] == 0
    assert out["results"][0]["documentDenominator"] == 10
    assert out["results"][0]["commentDenominator"] == 2


def test_row_docket_key_accepts_id_for_mocks():
    db = _FakeDbMerge(
        sql_rows=[{"id": 1, "title": "x", "cfr_refs": []}],
        os_hits=[],
        by_id_rows=[],
    )
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=2)
    assert out["results"][0]["match_source"] == "title"
    assert out["results"][0]["documentNumerator"] == 0
    assert out["results"][0]["commentNumerator"] == 0
    assert out["results"][0]["documentDenominator"] == 0
    assert out["results"][0]["commentDenominator"] == 0


def test_merge_full_text_dropped_when_agency_filter_no_match():
    """OpenSearch-only dockets must satisfy the same agency filter as title search."""
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": [], "agency_id": "CMS"}]
    os_hits = [
        {"docket_id": "A", "document_match_count": 1, "comment_match_count": 0},
        {"docket_id": "B", "document_match_count": 5, "comment_match_count": 1},
    ]
    by_id_rows = [
        {"docket_id": "B", "docket_title": "tb", "cfr_refs": [], "agency_id": "EPA"},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", agency=["CMS"], page=1, page_size=10)
    assert len(out["results"]) == 1
    assert out["results"][0]["docket_id"] == "A"
    assert db.get_dockets_by_ids_calls == [["B"]]


def test_merge_full_text_kept_when_agency_filter_matches():
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": [], "agency_id": "CMS"}]
    os_hits = [
        {"docket_id": "B", "document_match_count": 2, "comment_match_count": 0},
    ]
    by_id_rows = [
        {"docket_id": "B", "docket_title": "tb", "cfr_refs": [], "agency_id": "CMS-FOO"},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", agency=["CMS"], page=1, page_size=10)
    # A is a title/docket-id match, B is OpenSearch-only — title matches now
    # rank above FT-only hits regardless of comment-text match count.
    assert [r["docket_id"] for r in out["results"]] == ["A", "B"]


def test_merge_full_text_dropped_when_docket_type_filter_no_match():
    sql_rows = [
        {"docket_id": "A", "docket_title": "ta", "cfr_refs": [], "agency_id": "X",
         "docket_type": "Rulemaking"},
    ]
    os_hits = [{"docket_id": "B", "document_match_count": 1, "comment_match_count": 0}]
    by_id_rows = [
        {"docket_id": "B", "docket_title": "tb", "cfr_refs": [], "agency_id": "X",
         "docket_type": "Notice"},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", docket_type_param="Rulemaking", page=1, page_size=10)
    assert len(out["results"]) == 1
    assert out["results"][0]["docket_id"] == "A"


def test_merge_full_text_dropped_when_cfr_part_filter_no_match():
    sql_rows = [
        {"docket_id": "A", "docket_title": "ta", "cfr_refs": [
            {"title": "Title 42", "cfrParts": {"413": "http://a"}},
        ], "agency_id": "CMS"},
    ]
    os_hits = [{"docket_id": "B", "document_match_count": 1, "comment_match_count": 0}]
    by_id_rows = [
        {"docket_id": "B", "docket_title": "tb", "cfr_refs": [
            {"title": "Title 40", "cfrParts": {"99": "http://b"}},
        ], "agency_id": "CMS"},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search(
        "q",
        cfr_part_param=[{"title": "42 CFR", "part": "413"}],
        page=1,
        page_size=10,
    )
    assert len(out["results"]) == 1
    assert out["results"][0]["docket_id"] == "A"


def test_merge_os_hits_all_title_matches_falls_back_to_title_only():
    """OpenSearch returns hits but none are new vs title search → no get_dockets_by_ids."""
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": []}]
    os_hits = [{"docket_id": "A", "document_match_count": 9, "comment_match_count": 1}]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows=[])
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    assert len(out["results"]) == 1
    assert out["results"][0]["match_source"] == "title"
    assert out["results"][0]["documentNumerator"] == 9
    assert out["results"][0]["commentNumerator"] == 1
    assert out["results"][0]["documentDenominator"] == 10
    assert out["results"][0]["commentDenominator"] == 2
    assert not db.get_dockets_by_ids_calls


def test_merge_duplicate_os_hits_for_same_docket_only_fetch_once():
    """Second OpenSearch row with the same docket_id is skipped in _get_new_docket_ids."""
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": []}]
    os_hits = [
        {"docket_id": "B", "document_match_count": 1, "comment_match_count": 0},
        {"docket_id": "B", "document_match_count": 1, "comment_match_count": 0},
    ]
    by_id_rows = [{"docket_id": "B", "docket_title": "tb", "cfr_refs": []}]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", page=1, page_size=10)
    assert db.get_dockets_by_ids_calls == [["B"]]
    b_rows = [r for r in out["results"] if r["docket_id"] == "B"]
    assert len(b_rows) == 1
    assert b_rows[0]["documentNumerator"] == 1


def test_merge_full_text_kept_when_cfr_pattern_filter_matches():
    """Non-dict CFR filter (substring patterns) uses _cfr_part_patterns_match_row."""
    sql_rows = [{"docket_id": "A", "docket_title": "ta", "cfr_refs": [], "agency_id": "CMS"}]
    os_hits = [{"docket_id": "B", "document_match_count": 1, "comment_match_count": 0}]
    by_id_rows = [
        {
            "docket_id": "B",
            "docket_title": "tb",
            "cfr_refs": [{"title": "42", "cfrParts": {"413": "http://x"}}],
            "agency_id": "CMS",
        },
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", cfr_part_param=["413"], page=1, page_size=10)
    # Title match A outranks FT-only B even though B has higher AOSS counts.
    assert [r["docket_id"] for r in out["results"]] == ["A", "B"]


class _FakePagingDb:
    """db_layer for testing page-2 ordering on the fast path.

    Returns 25 OS-only hits with descending match counts so we can assert that
    page 2 (size 10) returns the next 10 by match count, not an arbitrary slice.
    """

    def __init__(self):
        self.fetch_calls = []
        self._all_rows = {
            f"D{i:02d}": {"docket_id": f"D{i:02d}", "docket_title": f"t{i}", "cfr_refs": []}
            for i in range(25)
        }

    def search(self, *_a, **_kw):
        return []

    def text_match_terms(self, _terms, opensearch_client=None):  # pylint: disable=unused-argument
        # Higher i → higher match count, so D24 ranks first, D00 last.
        return [
            {"docket_id": f"D{i:02d}", "document_match_count": i, "comment_match_count": 0}
            for i in range(25)
        ]

    def get_dockets_by_ids(self, docket_ids):
        self.fetch_calls.append(list(docket_ids))
        return [self._all_rows[d] for d in docket_ids if d in self._all_rows]

    def get_docket_document_comment_totals(self, docket_ids, opensearch_client=None):  # pylint: disable=unused-argument
        return {str(d): {"document_total_count": 0, "comment_total_count": 0} for d in docket_ids}


def test_pagination_page_two_returns_next_ten_by_match_count():
    """Fast path: page 2 must contain the next 10 dockets by match count, not the
    arbitrary slice of unsorted candidates that the original perf commit returned.
    """
    db = _FakePagingDb()
    logic = InternalLogic("x", db_layer=db)

    page1 = logic.search("q", page=1, page_size=10)
    page2 = logic.search("q", page=2, page_size=10)

    page1_ids = [r["docket_id"] for r in page1["results"]]
    page2_ids = [r["docket_id"] for r in page2["results"]]

    assert page1_ids == [f"D{i:02d}" for i in range(24, 14, -1)]
    assert page2_ids == [f"D{i:02d}" for i in range(14, 4, -1)]
    assert page1["pagination"]["total_results"] == 25
    assert page1["pagination"]["total_pages"] == 3
    # Fast path must only fetch RDS for the 10 IDs on the requested page.
    assert all(len(call) == 10 for call in db.fetch_calls)


def test_filtered_total_results_matches_filtered_set():
    """Slow path: total_results reflects the filtered count, not the
    pre-filter OpenSearch hit count."""
    sql_rows = []
    # 5 OS-only hits, but only 2 will survive the agency filter.
    os_hits = [
        {"docket_id": f"D{i}", "document_match_count": i, "comment_match_count": 0}
        for i in range(5)
    ]
    by_id_rows = [
        {"docket_id": "D0", "docket_title": "t", "cfr_refs": [], "agency_id": "EPA"},
        {"docket_id": "D1", "docket_title": "t", "cfr_refs": [], "agency_id": "CMS"},
        {"docket_id": "D2", "docket_title": "t", "cfr_refs": [], "agency_id": "EPA"},
        {"docket_id": "D3", "docket_title": "t", "cfr_refs": [], "agency_id": "CMS"},
        {"docket_id": "D4", "docket_title": "t", "cfr_refs": [], "agency_id": "EPA"},
    ]
    db = _FakeDbMerge(sql_rows, os_hits, by_id_rows)
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("q", agency=["CMS"], page=1, page_size=10)

    ids = [r["docket_id"] for r in out["results"]]
    assert set(ids) == {"D1", "D3"}
    assert out["pagination"]["total_results"] == 2
    assert out["pagination"]["total_pages"] == 1


class _FakeDbCollectionDockets:
    """Minimal db_layer for InternalLogic.get_collection_dockets."""

    def get_collections(self, user_email):  # pylint: disable=unused-argument
        return [{"collection_id": 7, "docket_ids": ["DOCKET-1"]}]

    def get_dockets_by_ids(self, docket_ids):  # pylint: disable=unused-argument
        return [
            {
                "docket_id": "DOCKET-1",
                "docket_title": "T",
                "cfr_refs": [{"title": "40", "cfrParts": {"99": "u"}}],
                "modify_date": date(2024, 3, 1),
            }
        ]

    def get_docket_document_comment_totals(self, docket_ids, opensearch_client=None):  # pylint: disable=unused-argument
        return {"DOCKET-1": {"document_total_count": 5, "comment_total_count": 3}}


def test_search_marks_exact_docket_id_match():
    """Row whose docket_id matches the query (case-insensitive) gets the
    isExactMatch flag — the frontend uses this to anchor and highlight it."""
    sql_rows = [
        {"docket_id": "CMS-2025-0050", "docket_title": "ESRD PPS", "cfr_refs": []},
        {"docket_id": "CMS-2025-0099", "docket_title": "Other CMS rule", "cfr_refs": []},
    ]
    db = _FakeDbMerge(sql_rows, os_hits=[], by_id_rows=[])
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("cms-2025-0050", page=1, page_size=10)

    matched = [r for r in out["results"] if r.get("isExactMatch")]
    assert len(matched) == 1
    assert matched[0]["docket_id"] == "CMS-2025-0050"
    other = next(r for r in out["results"] if r["docket_id"] == "CMS-2025-0099")
    assert "isExactMatch" not in other


def test_search_no_exact_match_when_query_does_not_match_id():
    """Free-text queries that aren't a docket-id don't tag any row."""
    sql_rows = [
        {"docket_id": "CMS-2025-0050", "docket_title": "ESRD PPS", "cfr_refs": []},
    ]
    db = _FakeDbMerge(sql_rows, os_hits=[], by_id_rows=[])
    logic = InternalLogic("x", db_layer=db)
    out = logic.search("medicare", page=1, page_size=10)

    assert all("isExactMatch" not in r for r in out["results"])


def test_get_collection_dockets_non_empty_sanitizes_and_paginates():
    """Branch with docket_ids loads rows, sanitizes modify_date, returns slice + pagination."""
    logic = InternalLogic("x", db_layer=_FakeDbCollectionDockets())
    out = logic.get_collection_dockets(7, "user@example.com", page=1, page_size=10)
    assert out["pagination"]["total_results"] == 1
    assert out["pagination"]["total_pages"] == 1
    assert out["results"][0]["modify_date"] == "2024-03-01"
    assert "cfrPart" in out["results"][0]
    assert out["results"][0]["documentDenominator"] == 5
    assert out["results"][0]["commentDenominator"] == 3
