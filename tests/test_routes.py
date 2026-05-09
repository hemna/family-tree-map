import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Sign in with FamilySearch" in response.text


def test_login_redirects(client):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "familysearch.org" in response.headers["location"]


def test_select_lineage_without_session_redirects(client):
    response = client.get("/select-lineage", follow_redirects=False)
    assert response.status_code in (302, 303, 307)


def test_map_without_session_redirects(client):
    response = client.get("/map", follow_redirects=False)
    assert response.status_code in (302, 303, 307)


def test_ancestry_status_without_session(client):
    response = client.get("/api/ancestry-status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
