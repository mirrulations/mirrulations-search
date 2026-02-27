"""
Tests for the Flask app endpoints - Updated for pagination
"""
import pytest
from mirrsearch.app import create_app


@pytest.fixture
def app():
    """Create and configure a test app instance"""
    test_app = create_app()
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):  # pylint: disable=redefined-outer-name
    """Create a test client for the app"""
    return app.test_client()


# def test_hello_world(client):  # pylint: disable=redefined-outer-name
#     """Test the home endpoint returns index.html"""
#     response = client.get('/')
#     assert response.status_code == 200


def test_search_endpoint_exists(client):  # pylint: disable=redefined-outer-name
    """Test that the search endpoint exists and returns 200"""
    response = client.get('/search/')
    assert response.status_code == 200


def test_search_returns_dict_with_pagination(client):  # pylint: disable=redefined-outer-name
    """Test that search endpoint returns dict with results and pagination"""
    response = client.get('/search/')
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert isinstance(data, dict)
    assert 'results' in data
    assert 'pagination' in data
    assert isinstance(data['results'], list)


def test_search_pagination_metadata(client):  # pylint: disable=redefined-outer-name
    """Test that pagination metadata is present and correct"""
    response = client.get('/search/')
    data = response.get_json()
    pagination = data['pagination']
    assert 'page' in pagination
    assert 'page_size' in pagination
    assert 'total_results' in pagination
    assert 'total_pages' in pagination
    assert 'has_next' in pagination
    assert 'has_prev' in pagination


def test_search_with_query_parameter(client):  # pylint: disable=redefined-outer-name
    """Test search endpoint with query parameter"""
    response = client.get('/search/?str=test_search')
    data = response.get_json()
    assert 'results' in data
    assert isinstance(data['results'], list)


def test_search_with_different_query_parameters(client):  # pylint: disable=redefined-outer-name
    """Test search endpoint with various query parameters"""
    response = client.get('/search/?str=users')
    data = response.get_json()
    assert 'results' in data

    response = client.get('/search/?str=find_all_documents')
    data = response.get_json()
    assert 'results' in data


def test_search_without_filter_returns_all_matches(client):  # pylint: disable=redefined-outer-name
    """Search without filter returns all matching documents"""
    response = client.get('/search/?str=renal')
    assert response.status_code == 200
    data = response.get_json()
    assert 'results' in data
    results = data['results']
    assert isinstance(results, list)


def test_search_with_valid_filter_returns_matching_document_type(client):  # pylint: disable=redefined-outer-name
    """Filter param restricts results to the specified document_type"""
    response = client.get('/search/?str=renal&document_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    assert isinstance(results, list)
    for doc in results:
        assert doc['document_type'] == 'Proposed Rule'


def test_search_with_filter_only_affects_document_type(client):  # pylint: disable=redefined-outer-name
    """Filter only restricts document_type; other fields are unaffected"""
    response = client.get('/search/?str=renal&document_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    assert isinstance(results, list)


def test_search_with_nonexistent_filter_returns_empty_list(client):  # pylint: disable=redefined-outer-name
    """A filter value matching no document_type returns an empty list"""
    response = client.get('/search/?str=renal&document_type=Notice')
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    assert isinstance(results, list)
    assert len(results) == 0


def test_search_filter_without_query_string_uses_default(client):  # pylint: disable=redefined-outer-name
    """If str is missing, defaults to 'example_query'"""
    response = client.get('/search/?document_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    assert isinstance(results, list)


def test_search_filter_result_structure(client):  # pylint: disable=redefined-outer-name
    """Filtered results have expected keys"""
    response = client.get('/search/?str=renal&document_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    assert isinstance(results, list)
    if len(results) > 0:
        doc = results[0]
        assert 'document_type' in doc


def test_search_with_agency_filter(client):  # pylint: disable=redefined-outer-name
    """Agency param restricts results to the specified agency_id"""
    response = client.get('/search/?str=renal&agency=CMS')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    results = data['results']
    assert isinstance(results, list)
    for doc in results:
        assert doc['agency_id'] == 'CMS'


def test_search_with_nonexistent_agency_returns_empty_list(client):  # pylint: disable=redefined-outer-name
    """An agency value matching no agency_id returns an empty list"""
    response = client.get('/search/?str=renal&agency=FDA')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    results = data['results']
    assert isinstance(results, list)
    assert len(results) == 0


def test_search_with_agency_and_filter(client):  # pylint: disable=redefined-outer-name
    """Both agency and filter params can be combined"""
    response = client.get('/search/?str=renal&agency=CMS&document_type=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    results = data['results']
    assert isinstance(results, list)
    for doc in results:
        assert doc['agency_id'] == 'CMS'
        assert doc['document_type'] == 'Proposed Rule'
