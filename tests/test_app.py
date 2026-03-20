"""
Tests for the Flask app endpoints - Header-based pagination (returns list)
"""
import tempfile
import os
from unittest.mock import patch, MagicMock
import pytest
from mock_db import MockDBLayer
from mirrsearch.app import create_app
from mirrsearch.db import get_postgres_connection, get_opensearch_connection


@pytest.fixture
def app(tmp_path):
    """Create and configure a test app instance"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(dist_dir=str(dist), db_layer=MockDBLayer())
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):  # pylint: disable=redefined-outer-name
    """Create a test client for the app"""
    return app.test_client()


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


@patch('mirrsearch.db.psycopg2.connect')
def test_get_postgres_connection(mock_connect):
    """Test postgres connection"""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    with patch.dict(os.environ, {
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_NAME': 'test',
        'DB_USER': 'test',
        'DB_PASSWORD': 'test'
    }):
        result = get_postgres_connection()
        assert result.conn == mock_conn
        mock_connect.assert_called_once()


@patch('mirrsearch.db.OpenSearch')
def test_get_opensearch_connection(mock_opensearch):
    """Test opensearch connection"""
    get_opensearch_connection()
    mock_opensearch.assert_called_once()
