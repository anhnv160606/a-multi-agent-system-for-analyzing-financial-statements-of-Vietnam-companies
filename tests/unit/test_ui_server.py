"""
Unit tests for Phase 6 FastAPI Web Server (src/ui/server.py).
"""

from fastapi.testclient import TestClient
from src.ui.server import app

client = TestClient(app)


def test_serve_index_html():
    """Verify that root endpoint serves the HTML UI."""
    response = client.get("/")
    assert response.status_code == 200
    assert "RAG-Flow Alpha" in response.text
    assert "workspace-wrapper" in response.text


def test_list_documents_api():
    """Verify that /api/documents returns preloaded documents."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "documents" in data
    assert data["count"] >= 0


def test_analyze_empty_query_error():
    """Verify that empty query returns HTTP 400."""
    response = client.post("/api/analyze", json={"query": ""})
    assert response.status_code == 400
