"""
Tests for pagination functionality (header-based)
"""
# pylint: disable=duplicate-code
import pytest
from mirrsearch.app import create_app
from mirrsearch.internal_logic import InternalLogic


class MockDbLayer:  # pylint: disable=too-few-public-methods
    """Mock database layer for testing"""
    def search(self, query, document_type=None, agency=None, # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
               cfr_part=None, start_date=None, end_date=None, # pylint: disable=unused-argument
               exact_docket_id=None): # pylint: disable=unused-argument
        """Return 25 mock results for testing pagination"""
        # Unused parameters are intentional for interface compatibility
        _ = document_type, agency, cfr_part, exact_docket_id
        return [
            {
                "id": i,
                "title": f"Document {i}",
                "content": f"Content for {query}"
            }
            for i in range(1, 26)
        ]

    def text_match_terms(self, terms, opensearch_client=None):  # pylint: disable=unused-argument
        return []

    def get_dockets_by_ids(self, docket_ids):  # pylint: disable=unused-argument
        return []

    def get_docket_document_comment_totals(self, docket_ids, opensearch_client=None):  # pylint: disable=unused-argument
        return {}


class MockOAuthHandler:  # pylint: disable=too-few-public-methods
    """Mock OAuth handler that always authenticates as a test user"""
    def validate_jwt_token(self, token):  # pylint: disable=unused-argument
        return "Test User|test@example.com"


@pytest.fixture
def app():
    """Create test app with mock database"""
    mock_db = MockDbLayer()
    test_app = create_app(db_layer=mock_db, oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):  # pylint: disable=redefined-outer-name
    """Create test client"""
    c = app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    return c


# API Endpoint Tests - Header-based pagination

def test_search_returns_list_not_dict(client):  # pylint: disable=redefined-outer-name
    """Test search returns a list (not dict)"""
    response = client.get('/search/?str=test')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_search_default_pagination(client):  # pylint: disable=redefined-outer-name
    """Test search with default pagination (page 1, size 10)"""
    response = client.get('/search/?str=test')
    assert response.status_code == 200

    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 10

    # Check headers
    assert response.headers['X-Page'] == '1'
    assert response.headers['X-Page-Size'] == '10'
    assert response.headers['X-Total-Results'] == '25'
    assert response.headers['X-Total-Pages'] == '3'


def test_search_page_2(client):  # pylint: disable=redefined-outer-name
    """Test getting page 2 of results"""
    response = client.get('/search/?str=test&page=2')
    data = response.get_json()

    assert len(data) == 10
    assert response.headers['X-Page'] == '2'
    assert response.headers['X-Has-Prev'] == 'true'
    assert response.headers['X-Has-Next'] == 'true'


def test_search_last_page(client):  # pylint: disable=redefined-outer-name
    """Test getting last page with fewer results"""
    response = client.get('/search/?str=test&page=3')
    data = response.get_json()

    assert len(data) == 5
    assert response.headers['X-Page'] == '3'
    assert response.headers['X-Has-Next'] == 'false'
    assert response.headers['X-Has-Prev'] == 'true'


def test_search_custom_page_size(client):  # pylint: disable=redefined-outer-name
    """Test custom page size"""
    response = client.get('/search/?str=test&page_size=5')
    data = response.get_json()

    assert len(data) == 5
    assert response.headers['X-Page-Size'] == '5'
    assert response.headers['X-Total-Pages'] == '5'


def test_search_invalid_page_number(client):  # pylint: disable=redefined-outer-name
    """Test that invalid page numbers are handled"""
    response = client.get('/search/?str=test&page=0')

    assert response.headers['X-Page'] == '1'


def test_search_page_size_too_large(client):  # pylint: disable=redefined-outer-name
    """Test that page size is capped at 100"""
    response = client.get('/search/?str=test&page_size=999')

    assert response.headers['X-Page-Size'] == '10'


def test_search_empty_page(client):  # pylint: disable=redefined-outer-name
    """Test requesting a page beyond available results"""
    response = client.get('/search/?str=test&page=999')
    data = response.get_json()

    assert len(data) == 0
    assert response.headers['X-Page'] == '999'


# InternalLogic Unit Tests - These stay the same (internal logic still returns dict)

def test_internal_logic_pagination():
    """Test InternalLogic pagination directly"""
    mock_db = MockDbLayer()
    logic = InternalLogic("test_db", db_layer=mock_db)

    result = logic.search("test", page=1, page_size=10)

    assert len(result['results']) == 10
    assert result['pagination']['total_results'] == 25
    assert result['pagination']['total_pages'] == 3


def test_internal_logic_pagination_metadata():
    """Test pagination metadata is correct"""
    mock_db = MockDbLayer()
    logic = InternalLogic("test_db", db_layer=mock_db)

    # First page
    result = logic.search("test", page=1, page_size=10)
    assert result['pagination']['has_prev'] is False
    assert result['pagination']['has_next'] is True

    # Middle page
    result = logic.search("test", page=2, page_size=10)
    assert result['pagination']['has_prev'] is True
    assert result['pagination']['has_next'] is True

    # Last page
    result = logic.search("test", page=3, page_size=10)
    assert result['pagination']['has_prev'] is True
    assert result['pagination']['has_next'] is False


def test_internal_logic_correct_results_slicing():  # pylint: disable=too-many-locals
    """Pagination must cover every result exactly once across pages, with no
    overlap or gaps. Order across pages is determined by the active sort, not
    by the order MockDbLayer happens to return rows in.
    """
    mock_db = MockDbLayer()
    logic = InternalLogic("test_db", db_layer=mock_db)

    page1 = logic.search("test", page=1, page_size=10)["results"]
    page2 = logic.search("test", page=2, page_size=10)["results"]
    page3 = logic.search("test", page=3, page_size=10)["results"]

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5

    page1_ids = [r["id"] for r in page1]
    page2_ids = [r["id"] for r in page2]
    page3_ids = [r["id"] for r in page3]
    all_ids = page1_ids + page2_ids + page3_ids
    assert len(set(all_ids)) == 25
    assert set(all_ids) == set(range(1, 26))
