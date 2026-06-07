"""
Unit tests for the CloudPulse Flask app.

Run locally with:
    pytest -v

These tests use Flask's built-in test client, so no running server is needed.
"""
import pytest

from main import app


@pytest.fixture
def client():
    """Provide a Flask test client for each test."""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_home_returns_200(client):
    """The home page should load successfully."""
    response = client.get("/")
    assert response.status_code == 200


def test_home_renders_html(client):
    """The home page should return HTML content."""
    response = client.get("/")
    assert response.content_type.startswith("text/html")


def test_health_returns_200(client):
    """The health endpoint should respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok_status(client):
    """The health endpoint should report status 'ok' as JSON."""
    response = client.get("/health")
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_unknown_route_returns_404(client):
    """An unknown route should return HTTP 404."""
    response = client.get("/does-not-exist")
    assert response.status_code == 404
