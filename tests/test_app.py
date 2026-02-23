"""
Tests for the Flask app endpoints.
Uses MockDBLayer injected via the `client` fixture in conftest.py.
"""
# pylint: disable=redefined-outer-name
import pytest


def test_home_endpoint(client):
    """Test the home endpoint returns the index.html template"""
    response = client.get('/')
    assert response.status_code == 200


def test_search_endpoint_exists(client):
    """Test that the search endpoint exists and returns 200"""
    response = client.get('/search/')
    assert response.status_code == 200


def test_search_returns_list(client):
    """Test that search endpoint returns a JSON list"""
    response = client.get('/search/')
    assert response.status_code == 200
    assert response.is_json
    assert isinstance(response.get_json(), list)


def test_search_returns_dummy_data(client):
    """Test that search endpoint returns expected mock data"""
    response = client.get('/search/?str=ESRD')
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert 'docket_id' in data[0]
    assert 'title' in data[0]
    assert 'ESRD' in data[0]['title'] or 'End-Stage Renal Disease' in data[0]['title']


def test_search_with_query_parameter(client):
    """Test that search endpoint accepts and filters by query parameter"""
    response = client.get('/search/?str=ESRD')
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any('ESRD' in item['title'] for item in data)


def test_search_with_different_query_parameters(client):
    """Test search endpoint with various query strings"""
    # By docket ID
    data1 = client.get('/search/?str=CMS-2025-024').get_json()
    assert isinstance(data1, list)
    assert len(data1) > 0
    assert all(item['docket_id'].startswith('CMS-2025-024') for item in data1)

    # By partial title
    data2 = client.get('/search/?str=ESRD').get_json()
    assert isinstance(data2, list)
    assert len(data2) > 0
    assert any('ESRD' in item['title'] for item in data2)

    # By agency ID
    data3 = client.get('/search/?str=CMS').get_json()
    assert isinstance(data3, list)
    assert len(data3) > 0
    assert all(item['agency_id'] == 'CMS' for item in data3)


@pytest.mark.integration
def test_search_with_postgres_seed_data(client):
    """Integration test: requires Postgres with seed data."""
    pytest.skip("Integration test requires USE_POSTGRES=true and a live DB")


def test_search_without_filter_returns_all_matches(client):
    """Omitting filter returns all matching results regardless of document_type"""
    response = client.get('/search/?str=renal')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert len({item['document_type'] for item in data}) >= 1


def test_search_with_valid_filter_returns_matching_document_type(client):
    """filter param restricts results to the specified document_type"""
    response = client.get('/search/?str=renal&filter=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(item['document_type'] == 'Proposed Rule' for item in data)


def test_search_with_filter_only_affects_document_type(client):
    """Filtered results still match the search query"""
    response = client.get('/search/?str=ESRD&filter=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for item in data:
        assert 'ESRD' in item['title'] or 'esrd' in item['title'].lower()
        assert item['document_type'] == 'Proposed Rule'


def test_search_with_nonexistent_filter_returns_empty_list(client):
    """A filter value matching no document_type returns an empty list"""
    response = client.get('/search/?str=renal&filter=Final Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_search_filter_is_case_insensitive(client):
    """Filter comparison is case-insensitive"""
    data_lower = client.get('/search/?str=renal&filter=proposed rule').get_json()
    data_upper = client.get('/search/?str=renal&filter=PROPOSED RULE').get_json()
    data_mixed = client.get('/search/?str=renal&filter=Proposed Rule').get_json()
    assert len(data_lower) == len(data_upper) == len(data_mixed)
    assert data_lower == data_upper == data_mixed


def test_search_filter_without_query_string_uses_default(client):
    """filter works even when no str param is provided (falls back to example_query)"""
    response = client.get('/search/?filter=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    # "example_query" matches nothing in mock data
    assert len(data) == 0


def test_search_filter_result_structure(client):
    """Filtered results contain all required fields"""
    response = client.get('/search/?str=CMS&filter=Proposed Rule')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    required_fields = ['docket_id', 'title', 'cfrPart', 'agency_id', 'document_type']
    for item in data:
        for field in required_fields:
            assert field in item, f"Filtered result missing field: {field}"
            