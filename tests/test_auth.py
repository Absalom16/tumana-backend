import pytest
from app import create_app, db


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_register(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test User",
            "phone": "+254712345678",
            "email": "test@example.com",
            "password": "Pass@1234",
            "role": "customer",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["requires_verification"] is True


def test_login_invalid(client):
    response = client.post(
        "/api/auth/login",
        json={"identifier": "nonexistent@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
