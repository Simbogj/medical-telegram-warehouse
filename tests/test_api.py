"""API unit tests using FastAPI TestClient with mocked database."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture
def mock_query():
    with patch("api.main.execute_query") as mock:
        yield mock


def test_health_check(mock_query):
    mock_query.return_value = [(1,)]
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_top_products(mock_query):
    mock_query.return_value = [("paracetamol", 5), ("vitamin", 3)]
    response = client.get("/api/reports/top-products?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["product"] == "paracetamol"


def test_channel_activity_not_found(mock_query):
    mock_query.return_value = []
    response = client.get("/api/channels/unknown/activity")
    assert response.status_code == 404


def test_search_messages(mock_query):
    mock_query.return_value = [
        (1001, "chemed", "2026-06-28", "Paracetamol 500mg", 200, 5, True),
    ]
    response = client.get("/api/search/messages?query=paracetamol")
    assert response.status_code == 200
    assert response.json()["query"] == "paracetamol"
    assert len(response.json()["results"]) == 1


def test_visual_content(mock_query):
    mock_query.return_value = [
        ("chemed", 10, 6, 60.0, "product_display"),
    ]
    response = client.get("/api/reports/visual-content")
    assert response.status_code == 200
    assert response.json()["stats"][0]["visual_pct"] == 60.0
