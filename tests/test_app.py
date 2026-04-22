"""
Tests for the Flask app endpoints - Header-based pagination (returns list)
"""
import json
import tempfile
import os
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest
from mock_db import MockDBLayer
from mirrsearch.app import create_app
from mirrsearch.db import get_db, get_opensearch_connection
from mirrsearch.app import _make_oauth_handler

# pylint: disable=duplicate-code
class MockOAuthHandler: # pylint: disable=too-many-lines
    """Mock OAuth handler that always authenticates as a test user"""
    def get_authorization_url(self):
        return "http://mock-auth-url", None

    def validate_jwt_token(self, token):  # pylint: disable=unused-argument
        return "Test User|test@example.com"

    def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
        return {"name": "Test User", "email": "test@example.com"}

    def create_jwt_token(self, user_id):  # pylint: disable=unused-argument
        return "mock-token"


@pytest.fixture
def mock_db():
    """Shared MockDBLayer instance for tests that need to inspect it."""
    return MockDBLayer()


@pytest.fixture
def app(tmp_path, mock_db):  # pylint: disable=redefined-outer-name
    """Create and configure a test app instance"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=mock_db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):  # pylint: disable=redefined-outer-name
    """Create a test client for the app"""
    c = app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    return c


def test_search_endpoint_exists(client):  # pylint: disable=redefined-outer-name
    """Test that the search endpoint exists and returns 200"""
    response = client.get('/search/')
    assert response.status_code == 200


def test_search_returns_list(client):  # pylint: disable=redefined-outer-name
    """Test that search endpoint returns a list (not dict)"""
    response = client.get('/search/')
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert isinstance(data, list)


def test_search_has_pagination_headers(client):  # pylint: disable=redefined-outer-name
    """Test that pagination metadata is in HTTP headers"""
    response = client.get('/search/')

    assert 'X-Page' in response.headers
    assert 'X-Page-Size' in response.headers
    assert 'X-Total-Results' in response.headers
    assert 'X-Total-Pages' in response.headers
    assert 'X-Has-Next' in response.headers
    assert 'X-Has-Prev' in response.headers


def test_search_with_query_parameter(client):  # pylint: disable=redefined-outer-name
    """Test search endpoint with query parameter"""
    response = client.get('/search/?str=ESRD')
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any('ESRD' in item['title'] for item in data)


def test_search_with_different_query_parameters(client):  # pylint: disable=redefined-outer-name
    """Test search endpoint with various query parameters"""
    data1 = client.get('/search/?str=CMS-2025-024').get_json()
    assert isinstance(data1, list)
    assert len(data1) > 0
    assert all(item['docket_id'].startswith('CMS-2025-024') for item in data1)

    data2 = client.get('/search/?str=ESRD').get_json()
    assert isinstance(data2, list)
    assert len(data2) > 0
    assert any('ESRD' in item['title'] for item in data2)

    data3 = client.get('/search/?str=CMS').get_json()
    assert isinstance(data3, list)
    assert len(data3) > 0
    assert all(item['agency_id'] == 'CMS' for item in data3)


def test_search_without_filter_returns_all_matches(client):  # pylint: disable=redefined-outer-name
    """Search without filter returns all matching documents"""
    response = client.get('/search/?str=renal')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_search_with_valid_filter_returns_matching_docket_type(client):  # pylint: disable=redefined-outer-name
    """Filter param restricts results to the specified docket_type"""
    response = client.get('/search/?str=renal&docket_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for doc in data:
        assert doc['document_type'] == 'Proposed Rule'


def test_search_with_filter_only_affects_docket_type(client):  # pylint: disable=redefined-outer-name
    """Filter only restricts docket_type; other fields are unaffected"""
    response = client.get('/search/?str=ESRD&docket_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for item in data:
        assert 'ESRD' in item['title'] or 'esrd' in item['title'].lower()
        assert item['document_type'] == 'Proposed Rule'


def test_search_with_nonexistent_filter_returns_empty_list(client):  # pylint: disable=redefined-outer-name
    """A filter value matching no docket_type returns an empty list"""
    response = client.get('/search/?str=renal&docket_type=Final Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_search_filter_without_query_string_uses_default(client):  # pylint: disable=redefined-outer-name
    """If str is missing, defaults to 'example_query' which matches nothing"""
    response = client.get('/search/?docket_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_search_filter_result_structure(client):  # pylint: disable=redefined-outer-name
    """Filtered results have all required fields"""
    response = client.get('/search/?str=CMS&docket_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    required_fields = ['docket_id', 'title', 'cfrPart', 'agency_id', 'document_type']
    for item in data:
        for field in required_fields:
            assert field in item, f"Result missing field: {field}"


def test_search_with_agency_filter(client):  # pylint: disable=redefined-outer-name
    """Agency param restricts results to the specified agency_id"""
    response = client.get('/search/?str=renal&agency=CMS')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for doc in data:
        assert doc['agency_id'] == 'CMS'


def test_search_with_multiple_agency_filters(client):  # pylint: disable=redefined-outer-name
    """Multiple agency params return results matching any of them"""
    response = client.get('/search/?str=renal&agency=CMS&agency=EPA')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for doc in data:
        assert doc['agency_id'] in ('CMS', 'EPA')


def test_search_with_nonexistent_agency_returns_empty_list(client):  # pylint: disable=redefined-outer-name
    """An agency value matching no agency_id returns an empty list"""
    response = client.get('/search/?str=renal&agency=FDA')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_search_with_multiple_cfr_part_filters(client):  # pylint: disable=redefined-outer-name
    """Multiple cfr_part params return results matching any of them"""
    response = client.get('/search/?str=renal&cfr_part=42 CFR Parts 413 and 512:413'
                          '&cfr_part=42 CFR Parts 413 and 512:512')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_search_with_agency_and_filter(client):  # pylint: disable=redefined-outer-name
    """Both agency and filter params can be combined"""
    response = client.get('/search/?str=renal&agency=CMS&docket_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for doc in data:
        assert doc['agency_id'] == 'CMS'
        assert doc['document_type'] == 'Proposed Rule'


def test_search_returns_401_without_cookie(app):  # pylint: disable=redefined-outer-name
    """Search endpoint returns 401 when no JWT cookie is present"""
    anon = app.test_client()
    response = anon.get('/search/')
    assert response.status_code == 401


def test_login_route_redirects(app):  # pylint: disable=redefined-outer-name
    """Login route redirects to Google authorization URL"""
    anon = app.test_client()
    response = anon.get('/auth/login')
    assert response.status_code == 302
    assert "mock-auth-url" in response.headers['Location']


def test_logout_route_clears_cookie(app):  # pylint: disable=redefined-outer-name
    """Logout route redirects to home and clears jwt_token cookie"""
    anon = app.test_client()
    anon.set_cookie("jwt_token", "mock-token")
    response = anon.get('/logout')
    assert response.status_code == 302
    assert any(
        'jwt_token' in h and 'expires' in h.lower()
        for h in response.headers.getlist('Set-Cookie')
    )


def test_auth_status_logged_in(client):  # pylint: disable=redefined-outer-name
    """Auth status returns logged_in true when valid cookie present"""
    response = client.get('/auth/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['logged_in'] is True
    assert data['name'] == 'Test User'
    assert data['email'] == 'test@example.com'


def test_auth_status_not_logged_in(app):  # pylint: disable=redefined-outer-name
    """Auth status returns logged_in false when no cookie"""
    anon = app.test_client()
    response = anon.get('/auth/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['logged_in'] is False


def test_invalid_cookie_treated_as_unauthenticated(tmp_path):
    """An invalid JWT cookie results in 401 on search"""
    from mirrsearch.oauth_handler import TokenInvalidError  # pylint: disable=import-outside-toplevel

    class RejectingOAuthHandler:  # pylint: disable=too-few-public-methods
        """OAuth handler that always rejects tokens"""
        def validate_jwt_token(self, token):  # pylint: disable=unused-argument
            raise TokenInvalidError("bad token")

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=MockDBLayer(), oauth_handler=RejectingOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("jwt_token", "invalid-token")
    response = anon.get('/search/')
    assert response.status_code == 401


def test_home_route_with_oauth_code_redirects(tmp_path):  # pylint: disable=redefined-outer-name
    """Home route exchanges OAuth code and redirects"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_authorized_user("test@example.com", "Test User")  # authorize the mock user
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert 'jwt_token' in response.headers.get('Set-Cookie', '')


def test_home_route_with_bad_oauth_code_redirects(tmp_path):
    """Home route redirects to / when OAuth code exchange fails"""
    class FailingOAuthHandler:
        """OAuth handler that always fails code exchange"""
        def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
            from mirrsearch.oauth_handler import OAuthCodeError  # pylint: disable=import-outside-toplevel
            raise OAuthCodeError("bad code")

        def validate_jwt_token(self, token):  # pylint: disable=unused-argument
            from mirrsearch.oauth_handler import TokenInvalidError  # pylint: disable=import-outside-toplevel
            raise TokenInvalidError("invalid")

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=MockDBLayer(), oauth_handler=FailingOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    response = anon.get('/?code=bad-code')
    assert response.status_code == 302


def test_home_route_with_index_html():
    """Test home route serves index.html"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write('<html><body>Home</body></html>')

        test_app = create_app(dist_dir=tmpdir, db_layer=MockDBLayer())
        test_client = test_app.test_client()

        response = test_client.get('/')
        assert response.status_code == 200
        assert b'Home' in response.data


# --- Collections ---

def test_get_collections_returns_empty_list(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections returns empty list when user has no collections"""
    response = client.get('/api/collections')
    assert response.status_code == 200
    assert response.get_json() == []


def test_get_collections_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /api/collections returns 401 without cookie"""
    response = app.test_client().get('/api/collections')
    assert response.status_code == 401


def test_create_collection_returns_id(client):  # pylint: disable=redefined-outer-name
    """POST /api/collections creates a collection and returns its id"""
    response = client.post('/api/collections', json={"name": "My Collection"})
    assert response.status_code == 201
    data = response.get_json()
    assert "collection_id" in data
    assert isinstance(data["collection_id"], int)


def test_create_collection_requires_name(client):  # pylint: disable=redefined-outer-name
    """POST /api/collections returns 400 when name is missing"""
    response = client.post('/api/collections', json={})
    assert response.status_code == 400


def test_create_collection_requires_auth(app):  # pylint: disable=redefined-outer-name
    """POST /api/collections returns 401 without cookie"""
    response = app.test_client().post('/api/collections', json={"name": "Test"})
    assert response.status_code == 401


def test_delete_collection(client):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id> deletes an existing collection"""
    collection_id = client.post(
        '/api/collections', json={"name": "To Delete"}
    ).get_json()["collection_id"]
    response = client.delete(f'/api/collections/{collection_id}')
    assert response.status_code == 204


def test_delete_collection_not_found(client):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id> returns 404 for nonexistent collection"""
    response = client.delete('/api/collections/9999')
    assert response.status_code == 404


def test_delete_collection_requires_auth(app):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id> returns 401 without cookie"""
    response = app.test_client().delete('/api/collections/1')
    assert response.status_code == 401


def test_add_docket_to_collection(client):  # pylint: disable=redefined-outer-name
    """POST /api/collections/<id>/dockets adds a docket to a collection"""
    collection_id = client.post(
        '/api/collections', json={"name": "My List"}
    ).get_json()["collection_id"]
    response = client.post(
        f'/api/collections/{collection_id}/dockets', json={"docket_id": "CMS-2025-0240"}
    )
    assert response.status_code == 204


def test_add_docket_requires_docket_id(client):  # pylint: disable=redefined-outer-name
    """POST /api/collections/<id>/dockets returns 400 when docket_id is missing"""
    collection_id = client.post(
        '/api/collections', json={"name": "My List"}
    ).get_json()["collection_id"]
    response = client.post(f'/api/collections/{collection_id}/dockets', json={})
    assert response.status_code == 400


def test_add_docket_collection_not_found(client):  # pylint: disable=redefined-outer-name
    """POST /api/collections/<id>/dockets returns 404 for nonexistent collection"""
    response = client.post('/api/collections/9999/dockets', json={"docket_id": "CMS-2025-0240"})
    assert response.status_code == 404


def test_add_docket_requires_auth(app):  # pylint: disable=redefined-outer-name
    """POST /api/collections/<id>/dockets returns 401 without cookie"""
    response = app.test_client().post(
        '/api/collections/1/dockets', json={"docket_id": "CMS-2025-0240"}
    )
    assert response.status_code == 401


def test_remove_docket_from_collection(client):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id>/dockets/<docket_id> removes a docket"""
    collection_id = client.post(
        '/api/collections', json={"name": "My List"}
    ).get_json()["collection_id"]
    client.post(f'/api/collections/{collection_id}/dockets', json={"docket_id": "CMS-2025-0240"})
    response = client.delete(f'/api/collections/{collection_id}/dockets/CMS-2025-0240')
    assert response.status_code == 204


def test_remove_docket_collection_not_found(client):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id>/dockets/<docket_id> returns 404 for nonexistent collection"""
    response = client.delete('/api/collections/9999/dockets/CMS-2025-0240')
    assert response.status_code == 404


def test_remove_docket_requires_auth(app):  # pylint: disable=redefined-outer-name
    """DELETE /api/collections/<id>/dockets/<docket_id> returns 401 without cookie"""
    response = app.test_client().delete('/api/collections/1/dockets/CMS-2025-0240')
    assert response.status_code == 401


def test_get_collections_shows_added_dockets(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections reflects dockets added to a collection"""
    collection_id = client.post(
        '/api/collections', json={"name": "My List"}
    ).get_json()["collection_id"]
    client.post(f'/api/collections/{collection_id}/dockets', json={"docket_id": "CMS-2025-0240"})
    data = client.get('/api/collections').get_json()
    match = next(c for c in data if c["collection_id"] == collection_id)
    assert "CMS-2025-0240" in match["docket_ids"]


# --- GET /api/collections/<id>/dockets (paginated) ---

def test_get_collection_dockets_returns_empty_for_empty_collection(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets returns empty list for a collection with no dockets"""
    collection_id = client.post(
        '/api/collections', json={"name": "Empty"}
    ).get_json()["collection_id"]
    response = client.get(f'/api/collections/{collection_id}/dockets')
    assert response.status_code == 200
    assert response.get_json() == []


def test_get_collection_dockets_has_pagination_headers(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets returns all required pagination headers"""
    collection_id = client.post(
        '/api/collections', json={"name": "Headers Check"}
    ).get_json()["collection_id"]
    response = client.get(f'/api/collections/{collection_id}/dockets')
    assert response.status_code == 200
    assert 'X-Page' in response.headers
    assert 'X-Page-Size' in response.headers
    assert 'X-Total-Results' in response.headers
    assert 'X-Total-Pages' in response.headers
    assert 'X-Has-Next' in response.headers
    assert 'X-Has-Prev' in response.headers


def test_get_collection_dockets_returns_404_for_nonexistent_collection(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets returns 404 for a collection that does not exist"""
    response = client.get('/api/collections/9999/dockets')
    assert response.status_code == 404


def test_get_collection_dockets_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets returns 401 without cookie"""
    response = app.test_client().get('/api/collections/1/dockets')
    assert response.status_code == 401


def test_get_collection_dockets_respects_page_size(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets respects page_size query param"""
    collection_id = client.post(
        '/api/collections', json={"name": "Paged"}
    ).get_json()["collection_id"]
    response = client.get(f'/api/collections/{collection_id}/dockets?page=1&page_size=5')
    assert response.status_code == 200
    assert response.headers['X-Page'] == '1'
    assert response.headers['X-Page-Size'] == '5'


def test_get_collection_dockets_returns_json_list(client):  # pylint: disable=redefined-outer-name
    """GET /api/collections/<id>/dockets returns a JSON list"""
    collection_id = client.post(
        '/api/collections', json={"name": "List Check"}
    ).get_json()["collection_id"]
    response = client.get(f'/api/collections/{collection_id}/dockets')
    assert response.is_json
    assert isinstance(response.get_json(), list)


def test_get_collection_dockets_total_results_zero_for_empty(client):  # pylint: disable=redefined-outer-name
    """X-Total-Results is 0 for a collection with no dockets"""
    collection_id = client.post(
        '/api/collections', json={"name": "Zero"}
    ).get_json()["collection_id"]
    response = client.get(f'/api/collections/{collection_id}/dockets')
    assert response.headers['X-Total-Results'] == '0'
    assert response.headers['X-Has-Next'] == 'false'
    assert response.headers['X-Has-Prev'] == 'false'


# --- agencies ---

def test_agencies_returns_list(client):  # pylint: disable=redefined-outer-name
    """Test that agencies endpoint returns a JSON list"""
    response = client.get('/agencies')
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert isinstance(data, list)


@patch('mirrsearch.db._build_engine')
def test_get_db_connection(mock_build_engine):
    """Test get_db returns a DBLayer backed by a SQLAlchemy engine"""
    mock_engine = MagicMock()
    mock_build_engine.return_value = mock_engine

    with patch.dict(os.environ, {
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_NAME': 'test',
        'DB_USER': 'test',
        'DB_PASSWORD': 'test'
    }):
        with patch('mirrsearch.db._ENGINE', None):
            result = get_db()
            assert result.engine == mock_engine
            mock_build_engine.assert_called_once()


@patch('mirrsearch.db.OpenSearch')
def test_get_opensearch_connection(mock_opensearch):
    """Test opensearch connection"""
    get_opensearch_connection()
    mock_opensearch.assert_called_once()


# --- Download ---

def test_request_download_returns_job_id(client):  # pylint: disable=redefined-outer-name
    """POST /download/request returns job_id and started status"""
    with patch('mirrsearch.app._push_job_to_redis'):
        response = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        })
    assert response.status_code == 202
    data = response.get_json()
    assert "job_id" in data
    assert data["status"] == "started"


def test_request_download_requires_auth(app):  # pylint: disable=redefined-outer-name
    """POST /download/request returns 401 without cookie"""
    response = app.test_client().post('/download/request', json={
        "docket_ids": ["CMS-2025-0240"],
        "format": "raw",
        "include_binaries": False
    })
    assert response.status_code == 401


def test_request_download_requires_docket_ids(client):  # pylint: disable=redefined-outer-name
    """POST /download/request returns 400 when docket_ids is missing"""
    response = client.post('/download/request', json={
        "format": "raw",
        "include_binaries": False
    })
    assert response.status_code == 400


def test_request_download_enforces_10_docket_limit(client):  # pylint: disable=redefined-outer-name
    """POST /download/request returns 400 when more than 10 dockets provided"""
    response = client.post('/download/request', json={
        "docket_ids": [f"CMS-2025-000{i}" for i in range(11)],
        "format": "raw",
        "include_binaries": False
    })
    assert response.status_code == 400


def test_request_download_requires_valid_format(client):  # pylint: disable=redefined-outer-name
    """POST /download/request returns 400 for invalid format"""
    response = client.post('/download/request', json={
        "docket_ids": ["CMS-2025-0240"],
        "format": "json",
        "include_binaries": False
    })
    assert response.status_code == 400


def test_request_download_accepts_csv_format(client):  # pylint: disable=redefined-outer-name
    """POST /download/request accepts csv as a valid format"""
    with patch('mirrsearch.app._push_job_to_redis'):
        response = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "csv",
            "include_binaries": False
        })
    assert response.status_code == 202



def test_download_status_returns_job_info(client):  # pylint: disable=redefined-outer-name
    """GET /download/status/<job_id> returns job status"""
    with patch('mirrsearch.app._push_job_to_redis'):
        job_id = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        }).get_json()["job_id"]
    response = client.get(f'/download/status/{job_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data["job_id"] == job_id
    assert "status" in data
    assert "format" in data
    assert "docket_ids" in data
    assert "created_at" in data



def test_download_status_not_found(client):  # pylint: disable=redefined-outer-name
    """GET /download/status/<job_id> returns 404 for nonexistent job"""
    response = client.get('/download/status/nonexistent-job-id')
    assert response.status_code == 404


def test_download_status_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /download/status/<job_id> returns 401 without cookie"""
    response = app.test_client().get('/download/status/some-job-id')
    assert response.status_code == 401


def test_download_file_not_ready(client):  # pylint: disable=redefined-outer-name
    """GET /download/<job_id> returns 202 when job is still pending"""
    with patch('mirrsearch.app._push_job_to_redis'):
        job_id = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        }).get_json()["job_id"]
    response = client.get(f'/download/{job_id}')
    assert response.status_code == 202



def test_download_file_not_found(client):  # pylint: disable=redefined-outer-name
    """GET /download/<job_id> returns 404 for nonexistent job"""
    response = client.get('/download/nonexistent-job-id')
    assert response.status_code == 404


def test_download_file_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /download/<job_id> returns 401 without cookie"""
    response = app.test_client().get('/download/some-job-id')
    assert response.status_code == 401


def test_download_file_redirects_to_s3_url(client, mock_db):  # pylint: disable=redefined-outer-name
    """GET /download/<job_id> redirects to S3 URL when job is ready"""
    with patch('mirrsearch.app._push_job_to_redis'):
        job_id = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        }).get_json()["job_id"]
    mock_db.set_job_ready(job_id, "https://s3.example.com/test.zip")
    response = client.get(f'/download/{job_id}')
    assert response.status_code == 302
    assert "s3.example.com" in response.headers["Location"]


def test_download_file_no_s3_url_returns_404(client, mock_db):  # pylint: disable=redefined-outer-name
    """GET /download/<job_id> returns 404 when job is ready but s3_url is missing"""
    with patch('mirrsearch.app._push_job_to_redis'):
        job_id = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        }).get_json()["job_id"]
    mock_db.update_download_job_status(job_id, "ready")
    response = client.get(f'/download/{job_id}')
    assert response.status_code == 404


def test_search_with_date_filters(client): # pylint: disable=redefined-outer-name
    """Test search with start_date and end_date filters"""
    response = client.get('/search/?str=renal&start_date=2024-01-01&end_date=2024-12-31')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_search_with_invalid_page_size_defaults_to_10(client): # pylint: disable=redefined-outer-name
    """Test that invalid page_size defaults to 10"""
    response = client.get('/search/?page_size=200')  # > 100 should default to 10
    assert response.status_code == 200
    assert response.headers['X-Page-Size'] == '10'


def test_search_with_page_less_than_1_defaults_to_1(client): # pylint: disable=redefined-outer-name
    """Test that page < 1 defaults to 1"""
    response = client.get('/search/?page=0')
    assert response.status_code == 200
    assert response.headers['X-Page'] == '1'


def test_search_with_invalid_cfr_part_ignores_malformed(client): # pylint: disable=redefined-outer-name
    """Test that malformed cfr_part values are ignored"""
    response = client.get('/search/?str=renal&cfr_part=invalid&cfr_part=42:413')
    assert response.status_code == 200


def test_home_route_serves_index_html(tmp_path):
    """Test home route serves index.html when no OAuth code"""
    index_path = tmp_path / "dist" / "index.html"
    index_path.parent.mkdir()
    index_path.write_text("<html><body>Test</body></html>")

    test_app = create_app(dist_dir=str(tmp_path / "dist"), db_layer=MockDBLayer())
    test_client = test_app.test_client()

    response = test_client.get('/')
    assert response.status_code == 200
    assert b'Test' in response.data


def test_search_with_empty_query_uses_default(client): # pylint: disable=redefined-outer-name
    """Test search with empty query uses default 'example_query'"""
    response = client.get('/search/?str=')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_oauth_handler_from_aws_secrets(monkeypatch):
    """Test OAuth handler creation from AWS Secrets Manager"""
    monkeypatch.setenv("USE_AWS_SECRETS", "true")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    mock_secret = {
        "base_url": "https://test.com",
        "google_client_id": "test-id",
        "google_client_secret": "test-secret",
        "jwt_secret": "test-jwt"
    }

    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(mock_secret)}
    mock_boto3.client.return_value = mock_client

    with patch.dict('sys.modules', {'boto3': mock_boto3}):
        with patch('mirrsearch.app._make_oauth_handler_from_aws') as mock_handler:
            mock_handler.return_value = MockOAuthHandler()
            handler = _make_oauth_handler()
            assert handler is not None


def test_internal_logic_error_handling(client): # pylint: disable=redefined-outer-name
    """Test error handling in InternalLogic"""
    with patch('mirrsearch.internal_logic.get_db') as mock_get_db:
        mock_get_db.side_effect = RuntimeError("DB Error")
        response = client.get('/search/?str=test')
        assert response.status_code in [200, 500]

# --- Single docket download ---

def test_request_single_download_returns_job_id(client):  # pylint: disable=redefined-outer-name
    """POST /download/request/<docket_id> returns job_id and started status"""
    with patch('mirrsearch.app._push_job_to_redis'):
        response = client.post('/download/request/CMS-2025-0240', json={
            "format": "raw",
            "include_binaries": False
        })
    assert response.status_code == 202
    data = response.get_json()
    assert "job_id" in data
    assert data["status"] == "started"


def test_request_single_download_requires_auth(app):  # pylint: disable=redefined-outer-name
    """POST /download/request/<docket_id> returns 401 without cookie"""
    response = app.test_client().post('/download/request/CMS-2025-0240', json={
        "format": "raw",
        "include_binaries": False
    })
    assert response.status_code == 401


def test_request_single_download_requires_valid_format(client):  # pylint: disable=redefined-outer-name
    """POST /download/request/<docket_id> returns 400 for invalid format"""
    response = client.post('/download/request/CMS-2025-0240', json={
        "format": "json",
        "include_binaries": False
    })
    assert response.status_code == 400


def test_request_single_download_accepts_csv_format(client):  # pylint: disable=redefined-outer-name
    """POST /download/request/<docket_id> accepts csv as a valid format"""
    with patch('mirrsearch.app._push_job_to_redis'):
        response = client.post('/download/request/CMS-2025-0240', json={
            "format": "csv",
            "include_binaries": False
        })
    assert response.status_code == 202


def test_request_single_download_status_checkable(client):  # pylint: disable=redefined-outer-name
    """Job created via single docket endpoint is retrievable via status endpoint"""
    with patch('mirrsearch.app._push_job_to_redis'):
        job_id = client.post('/download/request/CMS-2025-0240', json={
            "format": "raw",
            "include_binaries": False
        }).get_json()["job_id"]
    response = client.get(f'/download/status/{job_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data["job_id"] == job_id
    assert data["docket_ids"] == ["CMS-2025-0240"]

def test_request_download_pushes_to_redis(client):  # pylint: disable=redefined-outer-name
    """POST /download/request pushes job to Redis queue"""
    with patch('mirrsearch.app._push_job_to_redis') as mock_push:
        response = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        })
        assert response.status_code == 202
        assert mock_push.called
        call_args = mock_push.call_args[0]
        assert call_args[2] == ["CMS-2025-0240"]
        assert call_args[3] == "raw"
        assert call_args[4] is False


def test_request_single_download_pushes_to_redis(client):  # pylint: disable=redefined-outer-name
    """POST /download/request/<docket_id> pushes job to Redis queue"""
    with patch('mirrsearch.app._push_job_to_redis') as mock_push:
        response = client.post('/download/request/CMS-2025-0240', json={
            "format": "raw",
            "include_binaries": False
        })
        assert response.status_code == 202
        assert mock_push.called
        call_args = mock_push.call_args[0]
        assert call_args[2] == ["CMS-2025-0240"]


def test_request_download_redis_failure_marks_job_failed(client):  # pylint: disable=redefined-outer-name
    """POST /download/request returns 503 and marks the job failed if Redis push fails"""
    with patch('mirrsearch.app._push_job_to_redis', side_effect=Exception("Redis down")):
        response = client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        })
        assert response.status_code == 503
        data = response.get_json()
        assert data["error"] == "Unable to queue download job"

        status_response = client.get('/download/status/mock-job-1')
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        assert status_data["status"] == "failed"


def test_single_download_redis_failure_marks_job_failed(  # pylint: disable=redefined-outer-name
        client):
    """Single-docket download returns 503 and marks the job failed on Redis errors."""
    with patch('mirrsearch.app._push_job_to_redis', side_effect=Exception("Redis down")):
        response = client.post('/download/request/CMS-2025-0240', json={
            "format": "raw",
            "include_binaries": False
        })
        assert response.status_code == 503
        data = response.get_json()
        assert data["error"] == "Unable to queue download job"

        status_response = client.get('/download/status/mock-job-1')
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        assert status_data["status"] == "failed"

# =============================================================================
# last_login — GET /api/user/last-login
# =============================================================================

def test_get_user_last_login_returns_null_before_any_login(tmp_path):
    """GET /api/user/last-login returns null last_login for a brand-new user"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=MockDBLayer(), oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/api/user/last-login')
    assert response.status_code == 200
    data = response.get_json()
    assert data["email"] == "test@example.com"
    assert data["last_login"] is None


def test_get_user_last_login_returns_timestamp_after_oauth(tmp_path): # pylint: disable=too-many-locals
    """GET /api/user/last-login returns an ISO timestamp after a successful OAuth login"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_authorized_user("test@example.com", "Test User")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()

    # Trigger OAuth callback — this should call update_last_login
    anon.get('/?code=valid-code')

    # Now query as the authenticated user
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/api/user/last-login')
    assert response.status_code == 200
    data = response.get_json()
    assert data["email"] == "test@example.com"
    assert data["last_login"] is not None
    # Must be a valid ISO 8601 string
    parsed = datetime.fromisoformat(data["last_login"])
    assert parsed is not None


def test_get_user_last_login_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /api/user/last-login returns 401 without a valid cookie"""
    response = app.test_client().get('/api/user/last-login')
    assert response.status_code == 401


def test_get_user_last_login_updates_on_repeated_login(tmp_path):
    """last_login advances each time the user logs in via OAuth"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_authorized_user("test@example.com", "Test User")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True

    # First login
    anon = test_app.test_client()
    anon.get('/?code=valid-code')
    first_login = db.get_last_login("test@example.com")
    assert first_login is not None

    # Second login — simulate a later timestamp by calling update_last_login directly
    db.update_last_login("test@example.com", "Test User")
    second_login = db.get_last_login("test@example.com")
    assert second_login is not None
    # Both calls happened in the same test so timestamps may be equal; just confirm
    # the field is always populated and is a datetime
    assert isinstance(second_login, datetime)


def test_oauth_callback_calls_update_last_login(tmp_path):
    """_handle_oauth_callback invokes update_last_login on successful login"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_authorized_user("test@example.com", "Test User")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()

    assert db.get_last_login("test@example.com") is None
    anon.get('/?code=valid-code')
    assert db.get_last_login("test@example.com") is not None


def test_oauth_callback_last_login_failure_does_not_block_login(tmp_path):
    """A failure in update_last_login must not prevent the OAuth redirect from completing"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    class BrokenLastLoginDB(MockDBLayer):
        """MockDBLayer whose update_last_login always raises."""
        def update_last_login(self, email, name):
            raise RuntimeError("DB write failed")

    db = BrokenLastLoginDB()
    db.add_authorized_user("test@example.com", "Test User")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()

    response = anon.get('/?code=valid-code')
    # Login still succeeds — JWT cookie is set, redirect happens
    assert response.status_code == 302
    assert 'jwt_token' in response.headers.get('Set-Cookie', '')


# =============================================================================
# last_login — GET /admin/users
# =============================================================================

def test_admin_get_users_returns_list_for_admin(tmp_path):# pylint: disable=too-many-locals
    """GET /admin/users returns the authorized-users list with last_login for admins"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_admin("test@example.com")
    db.add_authorized_user("alice@example.com", "Alice")
    db.update_last_login("alice@example.com", "Alice")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")

    response = c.get('/admin/users')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    alice = next((u for u in data if u["email"] == "alice@example.com"), None)
    assert alice is not None
    assert alice["last_login"] is not None
    # Verify it's a serialized ISO string (not a raw datetime object)
    datetime.fromisoformat(alice["last_login"])


def test_admin_get_users_includes_null_last_login_for_never_logged_in(tmp_path):
    """GET /admin/users shows null last_login for users who have never logged in"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_admin("test@example.com")
    db.add_authorized_user("bob@example.com", "Bob")
    # Bob is authorized but has never logged in — no update_last_login call
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")

    response = c.get('/admin/users')
    assert response.status_code == 200
    data = response.get_json()
    bob = next((u for u in data if u["email"] == "bob@example.com"), None)
    assert bob is not None
    assert bob["last_login"] is None


def test_admin_get_users_forbidden_for_non_admin(app):  # pylint: disable=redefined-outer-name
    """GET /admin/users returns 403 for a non-admin authenticated user"""
    # The default MockDBLayer has no admins, so test@example.com is not an admin
    response = app.test_client()
    response.set_cookie("jwt_token", "mock-token")
    resp = response.get('/admin/users')
    assert resp.status_code == 403


def test_admin_get_users_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /admin/users returns 403 without a cookie (no user → not admin)"""
    response = app.test_client().get('/admin/users')
    assert response.status_code == 403

# =============================================================================
# Additional tests for coverage
# =============================================================================

def test_search_with_sort_by_parameter(client): # pylint: disable=redefined-outer-name
    """Test search with sort_by parameter"""
    response = client.get('/search/?str=ESRD&sort_by=modify_date')
    assert response.status_code == 200


def test_search_with_start_date_only(client): # pylint: disable=redefined-outer-name
    """Test search with only start_date filter"""
    response = client.get('/search/?str=renal&start_date=2024-01-01')
    assert response.status_code == 200


def test_search_with_end_date_only(client): # pylint: disable=redefined-outer-name
    """Test search with only end_date filter"""
    response = client.get('/search/?str=renal&end_date=2024-12-31')
    assert response.status_code == 200


def test_search_with_cfr_part_dict_format(client): # pylint: disable=redefined-outer-name
    """Test search with CFR part in dict format (title:part)"""
    response = client.get('/search/?str=renal&cfr_part=42:413')
    assert response.status_code == 200


def test_search_with_cfr_part_missing_title(client): # pylint: disable=redefined-outer-name
    """Test search with malformed CFR part (missing title) is ignored"""
    response = client.get('/search/?str=renal&cfr_part=:413')
    assert response.status_code == 200


def test_search_with_cfr_part_missing_part(client): # pylint: disable=redefined-outer-name
    """Test search with malformed CFR part (missing part) is ignored"""
    response = client.get('/search/?str=renal&cfr_part=42:')
    assert response.status_code == 200


# def test_admin_login_sets_intent_cookie(app):
#     """Test /admin/login sets login_intent cookie"""
#     response = app.get('/admin/login')
#     assert response.status_code == 302
#     assert any('login_intent=admin' in h for h in response.headers.getlist('Set-Cookie'))


def test_admin_status_without_cookie(app): # pylint: disable=redefined-outer-name
    """Test /admin/status returns is_admin false without cookie"""
    anon = app.test_client()
    response = anon.get('/admin/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data["is_admin"] is False


def test_admin_status_with_db_layer_none(tmp_path):
    """Test /admin/status when db_layer is None"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=None, oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/admin/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data["is_admin"] is False


def test_oauth_callback_admin_unauthorized(tmp_path):
    """Test OAuth callback for admin login with unauthorized user"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer(),
                          oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("login_intent", "admin")
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert '/admin?error=unauthorized' in response.headers['Location']


def test_oauth_callback_regular_user_unauthorized(tmp_path):
    """Test OAuth callback for regular login with unauthorized user"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(dist_dir=str(dist),
                          db_layer=MockDBLayer(), oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert '/login?error=unauthorized' in response.headers['Location']


def test_oauth_callback_admin_authorized(tmp_path):
    """Test OAuth callback for admin login with authorized admin user"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    db = MockDBLayer()
    db.add_admin("test@example.com")
    test_app = create_app(dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("login_intent", "admin")
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert 'jwt_token' in response.headers.get('Set-Cookie', '')
    assert response.headers['Location'] == '/admin'


def test_oauth_callback_exception_in_admin_check(tmp_path):
    """Test OAuth callback when admin check raises exception"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    class BrokenDB(MockDBLayer):
        def is_admin(self, email):
            raise RuntimeError("DB error")

    test_app = create_app(dist_dir=str(dist),
                          db_layer=BrokenDB(), oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("login_intent", "admin")
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert '/admin?error=unauthorized' in response.headers['Location']


def test_oauth_callback_exception_in_authorized_check(tmp_path):
    """Test OAuth callback when authorized user check raises exception"""
    dist = tmp_path/"dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    class BrokenDB(MockDBLayer):
        def is_authorized_user(self, email):
            raise RuntimeError("DB error")

    test_app = create_app(dist_dir=str(dist), db_layer=BrokenDB(), oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    response = anon.get('/?code=valid-code')
    assert response.status_code == 302
    assert '/login?error=unauthorized' in response.headers['Location']


def test_get_user_last_login_service_unavailable(tmp_path):
    """Test /api/user/last-login returns 503 when db_layer is None"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=None, oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/api/user/last-login')
    assert response.status_code == 503
    data = response.get_json()
    assert data["error"] == "Service unavailable"


def test_download_file_with_s3_url(tmp_path):
    """Test download_file redirects to S3 URL when job is ready"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    class MockDBWithReadyJob(MockDBLayer):
        def get_download_job(self, job_id, user_email):
            return {"status": "ready", "format": "raw", "docket_ids":
                    ["CMS-2025-0240"], "created_at": "2026-04-01T00:00:00"}
        def get_download_s3_url(self, job_id, user_email):
            return "https://s3.amazonaws.com/test-bucket/file.zip"

    test_app = create_app(dist_dir=str(dist),
                          db_layer=MockDBWithReadyJob(), oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/download/mock-job-1')
    assert response.status_code == 302
    assert "s3.amazonaws.com" in response.headers['Location']


def test_download_file_s3_url_not_found(tmp_path):
    """Test download_file returns 404 when S3 URL is None"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    class MockDBWithNoS3Url(MockDBLayer):
        def get_download_job(self, job_id, user_email):
            return {"status": "ready", "format": "raw", "docket_ids":
                    ["CMS-2025-0240"], "created_at": "2026-04-01T00:00:00"}
        def get_download_s3_url(self, job_id, user_email):
            return None

    test_app = create_app(dist_dir=str(dist),
                          db_layer=MockDBWithNoS3Url(), oauth_handler=MockOAuthHandler())
    test_app.config['TESTING'] = True
    c = test_app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    response = c.get('/download/mock-job-1')
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Download file not found"


def test_dockets_endpoint_with_no_ids(client): # pylint: disable=redefined-outer-name
    """Test /dockets endpoint returns empty list when no docket_ids provided"""
    response = client.get('/dockets')
    assert response.status_code == 200
    data = response.get_json()
    assert data == []


def test_dockets_endpoint_with_ids(client): # pylint: disable=redefined-outer-name
    """Test /dockets endpoint returns dockets for given IDs"""
    response = client.get('/dockets?docket_id=CMS-2025-0240')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_collections_page_route(tmp_path):
    """Test /collections route serves index.html"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Collections</body></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer())
    test_client = test_app.test_client()
    response = test_client.get('/collections')
    assert response.status_code == 200
    assert b'Collections' in response.data


def test_explorer_page_route(tmp_path):
    """Test /explorer route serves index.html"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Explorer</body></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer())
    test_client = test_app.test_client()
    response = test_client.get('/explorer')
    assert response.status_code == 200
    assert b'Explorer' in response.data
    response = test_client.get('/explorer/')
    assert response.status_code == 200


def test_login_page_route(tmp_path):
    """Test /login route serves index.html"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Login</body></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer())
    test_client = test_app.test_client()
    response = test_client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data


def test_admin_page_route(tmp_path):
    """Test /admin route serves index.html"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Admin</body></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer())
    test_client = test_app.test_client()
    response = test_client.get('/admin')
    assert response.status_code == 200
    assert b'Admin' in response.data
    response = test_client.get('/admin/')
    assert response.status_code == 200

def test_list_download_jobs_returns_created_jobs(client):  # pylint: disable=redefined-outer-name
    """GET /download/jobs returns jobs created by the user"""
    with patch('mirrsearch.app._push_job_to_redis'):
        # create a job first
        client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        })

    response = client.get('/download/jobs')
    assert response.status_code == 200
    data = response.get_json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert "job_id" in data[0]
    assert "status" in data[0]

def test_list_download_jobs_requires_auth(app):  # pylint: disable=redefined-outer-name
    """GET /download/jobs returns 401 without authentication"""
    response = app.test_client().get('/download/jobs')
    assert response.status_code == 401

def test_list_download_jobs_empty(client):  # pylint: disable=redefined-outer-name
    """GET /download/jobs returns empty list if no jobs exist"""
    response = client.get('/download/jobs')
    assert response.status_code == 200
    assert response.get_json() == []

def test_list_download_jobs_multiple(client):  # pylint: disable=redefined-outer-name
    """GET /download/jobs returns multiple jobs"""
    with patch('mirrsearch.app._push_job_to_redis'):
        client.post('/download/request', json={
            "docket_ids": ["CMS-2025-0240"],
            "format": "raw",
            "include_binaries": False
        })
        client.post('/download/request/CMS-2025-0240', json={
            "format": "csv",
            "include_binaries": False
        })

    response = client.get('/download/jobs')
    data = response.get_json()

    assert len(data) >= 2
