"""
Shared pytest fixtures for all tests.
"""
import pytest
from mock_db import MockDBLayer
from mirrsearch.app import create_app


@pytest.fixture
def mock_db():
    """Return a MockDBLayer instance with dummy data."""
    return MockDBLayer()


@pytest.fixture
def app(mock_db):
    """Create a test app that uses MockDBLayer instead of the real DB."""
    flask_app = create_app(db_layer=mock_db)
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Test client for the app."""
    return app.test_client()
