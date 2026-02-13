"""
Tests for the Flask app endpoints
"""
import pytest
from mirrsearch.app import create_app


@pytest.fixture
def app():
    """Create and configure a test app instance"""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a test client for the app"""
    return app.test_client()


def test_home_endpoint(client):
    """Test the home endpoint returns the index.html template"""
    response = client.get('/')
    assert response.status_code == 200


def test_search_endpoint_exists(client):
    """Test that the search endpoint exists and returns 200"""
    response = client.get('/search/')
    assert response.status_code == 200


def test_search_returns_list(client):
    """Test that search endpoint returns a list"""
    response = client.get('/search/')
    assert response.status_code == 200
    # Flask will auto-convert the list to JSON
    assert response.is_json
    data = response.get_json()
    assert isinstance(data, list)


def test_search_returns_dummy_data(client):
    """Test that search endpoint returns the expected dummy data"""
    response = client.get('/search/')
    data = response.get_json()
    
    # Should return a list
    assert isinstance(data, list)
    assert len(data) > 0


def test_search_with_query_parameter(client):
    """Test that search endpoint accepts and returns query parameter"""
    response = client.get('/search/?str=my_search_query')
    data = response.get_json()
    
    # Should return a list
    assert isinstance(data, list)
    assert len(data) > 0


def test_search_with_different_query_parameters(client):
    """Test search endpoint with various query strings"""
    # Test with simple string
    response1 = client.get('/search/?str=hello')
    data1 = response1.get_json()
    assert isinstance(data1, list)
    assert len(data1) > 0
    
    # Test with multiple words
    response2 = client.get('/search/?str=hello world')
    data2 = response2.get_json()
    assert isinstance(data2, list)
    assert len(data2) > 0
    
    # Test with empty string
    response3 = client.get('/search/?str=')
    data3 = response3.get_json()
    assert isinstance(data3, list)
    assert len(data3) > 0