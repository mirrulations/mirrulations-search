"""
Tests for admin endpoints in app.py and admin methods in MockDBLayer.
"""
import pytest
from mock_db import MockDBLayer
from mirrsearch.app import create_app


# pylint: disable=duplicate-code
class MockOAuthHandler:
    """Mock OAuth handler that always authenticates as a regular user"""
    def get_authorization_url(self):
        return "http://mock-auth-url", None

    def validate_jwt_token(self, token):  # pylint: disable=unused-argument
        return "Test User|test@example.com"

    def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
        return {"name": "Test User", "email": "test@example.com"}

    def create_jwt_token(self, user_id):  # pylint: disable=unused-argument
        return "mock-token"


class AdminOAuthHandler:
    """Mock OAuth handler that authenticates as the admin user"""
    def get_authorization_url(self):
        return "http://mock-auth-url", None

    def validate_jwt_token(self, token):  # pylint: disable=unused-argument
        return "Admin User|admin@example.com"

    def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
        return {"name": "Admin User", "email": "admin@example.com"}

    def create_jwt_token(self, user_id):  # pylint: disable=unused-argument
        return "admin-token"


@pytest.fixture
def db():
    return MockDBLayer()


@pytest.fixture
def app(tmp_path, db):  # pylint: disable=redefined-outer-name
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=MockOAuthHandler()
    )
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def admin_app(tmp_path, db):  # pylint: disable=redefined-outer-name
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db, oauth_handler=AdminOAuthHandler()
    )
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):  # pylint: disable=redefined-outer-name
    c = app.test_client()
    c.set_cookie("jwt_token", "mock-token")
    return c


@pytest.fixture
def admin_client(admin_app):  # pylint: disable=redefined-outer-name
    c = admin_app.test_client()
    c.set_cookie("jwt_token", "admin-token")
    return c


# --- MockDBLayer admin methods ---

def test_is_admin_returns_true_for_admin(db):  # pylint: disable=redefined-outer-name
    """is_admin returns True for the seeded admin email"""
    assert db.is_admin("admin@example.com") is True


def test_is_admin_returns_false_for_non_admin(db):  # pylint: disable=redefined-outer-name
    """is_admin returns False for a regular user"""
    assert db.is_admin("user@example.com") is False


def test_is_admin_case_insensitive(db):  # pylint: disable=redefined-outer-name
    """is_admin is case-insensitive"""
    assert db.is_admin("ADMIN@EXAMPLE.COM") is True


def test_get_authorized_users_empty_initially(db):  # pylint: disable=redefined-outer-name
    """get_authorized_users returns empty list initially"""
    assert db.get_authorized_users() == []


def test_add_authorized_user_and_retrieve(db):  # pylint: disable=redefined-outer-name
    """add_authorized_user adds user and get_authorized_users returns it"""
    db.add_authorized_user("user@example.com", "Test User")
    users = db.get_authorized_users()
    assert len(users) == 1
    assert users[0]["email"] == "user@example.com"
    assert users[0]["name"] == "Test User"


def test_add_authorized_user_normalizes_email(db):  # pylint: disable=redefined-outer-name
    """add_authorized_user lowercases the email"""
    db.add_authorized_user("USER@EXAMPLE.COM", "Test User")
    users = db.get_authorized_users()
    assert users[0]["email"] == "user@example.com"


def test_add_authorized_user_upserts(db):  # pylint: disable=redefined-outer-name
    """Adding the same email twice updates the record rather than duplicating it"""
    db.add_authorized_user("user@example.com", "Old Name")
    db.add_authorized_user("user@example.com", "New Name")
    users = db.get_authorized_users()
    assert len(users) == 1
    assert users[0]["name"] == "New Name"


def test_remove_authorized_user_returns_true(db):  # pylint: disable=redefined-outer-name
    """remove_authorized_user returns True when user is found and removed"""
    db.add_authorized_user("user@example.com", "Test User")
    assert db.remove_authorized_user("user@example.com") is True
    assert db.get_authorized_users() == []


def test_remove_authorized_user_returns_false_when_not_found(db):  # pylint: disable=redefined-outer-name
    """remove_authorized_user returns False when user does not exist"""
    assert db.remove_authorized_user("nobody@example.com") is False


def test_remove_authorized_user_case_insensitive(db):  # pylint: disable=redefined-outer-name
    """remove_authorized_user is case-insensitive"""
    db.add_authorized_user("user@example.com", "Test User")
    assert db.remove_authorized_user("USER@EXAMPLE.COM") is True


# --- MockDBLayer update_authorized_user_name ---

def test_update_authorized_user_name_returns_true(db):  # pylint: disable=redefined-outer-name
    """update_authorized_user_name returns True and updates the name"""
    db.add_authorized_user("user@example.com", "Old Name")
    assert db.update_authorized_user_name("user@example.com", "New Name") is True
    users = db.get_authorized_users()
    assert users[0]["name"] == "New Name"


def test_update_authorized_user_name_returns_false_when_not_found(db):  # pylint: disable=redefined-outer-name
    """update_authorized_user_name returns False when email does not exist"""
    assert db.update_authorized_user_name("nobody@example.com", "Whatever") is False


def test_update_authorized_user_name_case_insensitive(db):  # pylint: disable=redefined-outer-name
    """update_authorized_user_name matches email case-insensitively"""
    db.add_authorized_user("user@example.com", "Old Name")
    assert db.update_authorized_user_name("USER@EXAMPLE.COM", "New Name") is True
    users = db.get_authorized_users()
    assert users[0]["name"] == "New Name"


def test_update_authorized_user_name_preserves_other_fields(db):  # pylint: disable=redefined-outer-name
    """update_authorized_user_name does not alter email or authorized_at"""
    db.add_authorized_user("user@example.com", "Old Name")
    db.update_authorized_user_name("user@example.com", "New Name")
    users = db.get_authorized_users()
    assert users[0]["email"] == "user@example.com"
    assert users[0]["authorized_at"] == "2026-01-01T00:00:00"


# --- /admin/login endpoint ---

def test_admin_login_redirects_to_oauth(app):  # pylint: disable=redefined-outer-name
    """GET /admin/login redirects to OAuth authorization URL"""
    response = app.test_client().get('/admin/login')
    assert response.status_code == 302
    assert "mock-auth-url" in response.headers['Location']


def test_admin_login_sets_login_intent_cookie(app):  # pylint: disable=redefined-outer-name
    """GET /admin/login sets login_intent=admin cookie"""
    response = app.test_client().get('/admin/login')
    cookies = response.headers.getlist('Set-Cookie')
    assert any("login_intent=admin" in c for c in cookies)


# --- /admin/status endpoint ---

def test_admin_status_not_logged_in(app):  # pylint: disable=redefined-outer-name
    """GET /admin/status returns is_admin=False when no cookie"""
    response = app.test_client().get('/admin/status')
    assert response.status_code == 200
    assert response.get_json()["is_admin"] is False


def test_admin_status_non_admin_user(client):  # pylint: disable=redefined-outer-name
    """GET /admin/status returns is_admin=False for regular user"""
    response = client.get('/admin/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data["is_admin"] is False
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"


def test_admin_status_admin_user(admin_client):  # pylint: disable=redefined-outer-name
    """GET /admin/status returns is_admin=True for admin user"""
    response = admin_client.get('/admin/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data["is_admin"] is True
    assert data["email"] == "admin@example.com"


# --- /api/authorized GET ---

def test_get_authorized_users_forbidden_for_non_admin(client):  # pylint: disable=redefined-outer-name
    """GET /api/authorized returns 403 for non-admin user"""
    response = client.get('/api/authorized')
    assert response.status_code == 403


def test_get_authorized_users_forbidden_without_cookie(app):  # pylint: disable=redefined-outer-name
    """GET /api/authorized returns 403 when not logged in"""
    response = app.test_client().get('/api/authorized')
    assert response.status_code == 403


def test_get_authorized_users_returns_list_for_admin(admin_client):  # pylint: disable=redefined-outer-name
    """GET /api/authorized returns list for admin"""
    response = admin_client.get('/api/authorized')
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_get_authorized_users_shows_added_user(admin_client, db):  # pylint: disable=redefined-outer-name
    """GET /api/authorized reflects users added directly to db"""
    db.add_authorized_user("someone@example.com", "Someone")
    response = admin_client.get('/api/authorized')
    users = response.get_json()
    assert any(u["email"] == "someone@example.com" for u in users)


# --- /api/authorized POST ---

def test_add_authorized_user_forbidden_for_non_admin(client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized returns 403 for non-admin"""
    response = client.post('/api/authorized', json={"email": "x@x.com", "name": "X"})
    assert response.status_code == 403


def test_add_authorized_user_success(admin_client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized creates user and returns 201"""
    response = admin_client.post('/api/authorized',
                                 json={"email": "new@example.com", "name": "New User"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["email"] == "new@example.com"
    assert data["name"] == "New User"


def test_add_authorized_user_missing_email(admin_client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized returns 400 when email is missing"""
    response = admin_client.post('/api/authorized', json={"name": "No Email"})
    assert response.status_code == 400


def test_add_authorized_user_missing_name(admin_client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized returns 400 when name is missing"""
    response = admin_client.post('/api/authorized', json={"email": "x@x.com"})
    assert response.status_code == 400


def test_add_authorized_user_empty_body(admin_client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized returns 400 for empty body"""
    response = admin_client.post('/api/authorized', json={})
    assert response.status_code == 400


def test_add_authorized_user_reflects_in_get(admin_client):  # pylint: disable=redefined-outer-name
    """User added via POST appears in GET /api/authorized"""
    admin_client.post('/api/authorized', json={"email": "added@example.com", "name": "Added"})
    users = admin_client.get('/api/authorized').get_json()
    assert any(u["email"] == "added@example.com" for u in users)


# --- /api/authorized/<email> DELETE ---

def test_remove_authorized_user_forbidden_for_non_admin(client):  # pylint: disable=redefined-outer-name
    """DELETE /api/authorized/<email> returns 403 for non-admin"""
    response = client.delete('/api/authorized/someone@example.com')
    assert response.status_code == 403


def test_remove_authorized_user_success(admin_client, db):  # pylint: disable=redefined-outer-name
    """DELETE /api/authorized/<email> removes user and returns 204"""
    db.add_authorized_user("todelete@example.com", "To Delete")
    response = admin_client.delete('/api/authorized/todelete@example.com')
    assert response.status_code == 204


def test_remove_authorized_user_not_found(admin_client):  # pylint: disable=redefined-outer-name
    """DELETE /api/authorized/<email> returns 404 when user does not exist"""
    response = admin_client.delete('/api/authorized/nobody@example.com')
    assert response.status_code == 404


def test_remove_authorized_user_no_longer_in_list(admin_client, db):  # pylint: disable=redefined-outer-name
    """Removed user no longer appears in GET /api/authorized"""
    db.add_authorized_user("gone@example.com", "Gone")
    admin_client.delete('/api/authorized/gone@example.com')
    users = admin_client.get('/api/authorized').get_json()
    assert not any(u["email"] == "gone@example.com" for u in users)

def test_update_authorized_user_success(admin_client, db):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name updates the name and returns 200"""
    db.add_authorized_user("edit@example.com", "Old Name")
    response = admin_client.post(
        '/api/authorized/edit@example.com/update-name', json={"name": "New Name"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["email"] == "edit@example.com"
    assert data["name"] == "New Name"


def test_update_authorized_user_reflected_in_get(admin_client, db):  # pylint: disable=redefined-outer-name
    """Name change via POST /update-name is reflected in GET /api/authorized"""
    db.add_authorized_user("edit@example.com", "Old Name")
    admin_client.post('/api/authorized/edit@example.com/update-name', json={"name": "Updated Name"})
    users = admin_client.get('/api/authorized').get_json()
    match = next(u for u in users if u["email"] == "edit@example.com")
    assert match["name"] == "Updated Name"


def test_update_authorized_user_not_found(admin_client):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name returns 404 when user does not exist"""
    response = admin_client.post(
        '/api/authorized/nobody@example.com/update-name', json={"name": "Whoever"}
    )
    assert response.status_code == 404


def test_update_authorized_user_missing_name(admin_client, db):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name returns 400 when name is missing"""
    db.add_authorized_user("edit@example.com", "Old Name")
    response = admin_client.post('/api/authorized/edit@example.com/update-name', json={})
    assert response.status_code == 400


def test_update_authorized_user_blank_name(admin_client, db):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name returns 400 when name is blank"""
    db.add_authorized_user("edit@example.com", "Old Name")
    response = admin_client.post(
        '/api/authorized/edit@example.com/update-name', json={"name": "   "}
    )
    assert response.status_code == 400


def test_update_authorized_user_forbidden_for_non_admin(client, db):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name returns 403 for non-admin"""
    db.add_authorized_user("edit@example.com", "Old Name")
    response = client.post(
        '/api/authorized/edit@example.com/update-name', json={"name": "New Name"}
    )
    assert response.status_code == 403


def test_update_authorized_user_forbidden_without_cookie(app, db):  # pylint: disable=redefined-outer-name
    """POST /api/authorized/<email>/update-name returns 403 when not logged in"""
    db.add_authorized_user("edit@example.com", "Old Name")
    response = app.test_client().post(
        '/api/authorized/edit@example.com/update-name', json={"name": "New Name"}
    )
    assert response.status_code == 403


# --- /admin and /admin/ page routes ---

def test_admin_page_serves_html(app):  # pylint: disable=redefined-outer-name
    """GET /admin serves index.html"""
    response = app.test_client().get('/admin')
    assert response.status_code == 200


def test_admin_page_trailing_slash(app):  # pylint: disable=redefined-outer-name
    """GET /admin/ also serves index.html"""
    response = app.test_client().get('/admin/')
    assert response.status_code == 200


# --- _handle_oauth_callback with login_intent ---

def test_admin_oauth_callback_redirects_non_admin_to_error(tmp_path):
    """OAuth callback with admin intent redirects non-admin to /admin?error=unauthorized"""
    db_instance = MockDBLayer()

    class NonAdminOAuth:
        def get_authorization_url(self):
            return "http://mock", None
        def validate_jwt_token(self, token):  # pylint: disable=unused-argument
            from mirrsearch.oauth_handler import TokenInvalidError  # pylint: disable=import-outside-toplevel
            raise TokenInvalidError("no")
        def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
            return {"name": "Regular", "email": "regular@example.com"}
        def create_jwt_token(self, user_id):  # pylint: disable=unused-argument
            return "tok"

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db_instance, oauth_handler=NonAdminOAuth()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("login_intent", "admin")
    response = anon.get('/?code=some-code')
    assert response.status_code == 302
    assert "error=unauthorized" in response.headers['Location']


def test_admin_oauth_callback_redirects_admin_to_admin_page(tmp_path):
    """OAuth callback with admin intent redirects verified admin to /admin"""
    db_instance = MockDBLayer()

    class VerifiedAdminOAuth:
        def get_authorization_url(self):
            return "http://mock", None
        def validate_jwt_token(self, token):  # pylint: disable=unused-argument
            from mirrsearch.oauth_handler import TokenInvalidError  # pylint: disable=import-outside-toplevel
            raise TokenInvalidError("no")
        def exchange_code_for_user_info(self, code):  # pylint: disable=unused-argument
            return {"name": "Admin", "email": "admin@example.com"}
        def create_jwt_token(self, user_id):  # pylint: disable=unused-argument
            return "admin-tok"

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    test_app = create_app(
        dist_dir=str(dist), db_layer=db_instance, oauth_handler=VerifiedAdminOAuth()
    )
    test_app.config['TESTING'] = True
    anon = test_app.test_client()
    anon.set_cookie("login_intent", "admin")
    response = anon.get('/?code=admin-code')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin')
