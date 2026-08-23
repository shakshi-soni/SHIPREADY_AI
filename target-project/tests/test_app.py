"""
tests/test_app.py — Target project's real test suite.

This file is READ-ONLY to ShipReady by contract (see contract.yaml ->
test_files_unmodified). The agent may only fix app.py to make these
tests pass — it may never edit this file.

Right now, test_health_returns_healthy is EXPECTED TO FAIL: app.py has a
deliberate bug (/health returns "error" instead of "healthy"). That
failure is the whole point — it's what ShipReady discovers and repairs
during the demo.
"""

import pytest

from app import app, tasks


@pytest.fixture
def client():
    app.config["TESTING"] = True
    tasks.clear()  # reset shared state between tests
    with app.test_client() as c:
        yield c


def test_health_returns_healthy(client):
    """This test currently FAILS on purpose — app.py has a bug where
    /health returns {"status": "error"} instead of {"status": "healthy"}.
    ShipReady is expected to find and fix this."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "healthy"


def test_get_tasks_starts_empty(client):
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert resp.get_json()["tasks"] == []


def test_add_task_success(client):
    resp = client.post("/tasks", json={"title": "Submit ShipReady"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "Submit ShipReady"
    assert body["done"] is False
    assert body["id"] == 1


def test_add_task_missing_title_returns_400(client):
    resp = client.post("/tasks", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_added_task_appears_in_list(client):
    client.post("/tasks", json={"title": "First task"})
    client.post("/tasks", json={"title": "Second task"})
    resp = client.get("/tasks")
    titles = [t["title"] for t in resp.get_json()["tasks"]]
    assert titles == ["First task", "Second task"]