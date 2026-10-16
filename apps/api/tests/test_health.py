import json
import logging
import time
from uuid import UUID

import pytest


def test_healthy_database_returns_ok_and_request_id(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"]["status"] == "healthy"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert UUID(body["request_id"]).version == 4
    assert response.headers["cache-control"] == "no-store"


def test_database_failure_returns_503_without_exception_details(client_factory, caplog):
    caplog.set_level(logging.INFO, logger="agentradar")
    with client_factory("unhealthy") as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "p00-db-failure"})

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"]["status"] == "unhealthy"
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert body["error"]["message"]
    assert body["request_id"] == response.headers["X-Request-ID"] == "p00-db-failure"
    assert "must-not-leak" not in response.text + caplog.text


def test_database_check_has_a_bounded_timeout(client_factory):
    with client_factory("slow") as client:
        started = time.monotonic()
        response = client.get("/api/v1/health")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert elapsed < 1.5


def test_response_request_id_matches_structured_request_log(client, caplog):
    caplog.set_level(logging.INFO, logger="agentradar")
    response = client.get("/api/v1/health", headers={"X-Request-ID": "p00-trace-001"})

    records = [record for record in caplog.records if record.getMessage() == "request_completed"]
    assert len(records) == 1
    record = records[0]
    assert record.request_id == response.json()["request_id"] == "p00-trace-001"
    handler = logging.getLogger("agentradar").handlers[0]
    log = json.loads(handler.format(record))
    assert log["request_id"] == "p00-trace-001"
    assert log["status_code"] == 200
    assert log["path"] == "/api/v1/health"
    assert log["duration_ms"] >= 0


@pytest.mark.parametrize("incoming", ["unsafe id with spaces", "x" * 200])
def test_invalid_incoming_request_id_is_replaced(client, incoming):
    response = client.get("/api/v1/health", headers={"X-Request-ID": incoming})
    request_id = response.headers["X-Request-ID"]

    assert request_id != incoming
    assert UUID(request_id).version == 4
    assert response.json()["request_id"] == request_id
