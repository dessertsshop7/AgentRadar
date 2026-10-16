import logging

import pytest


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/api/v1/missing", 404, "HTTP_404"),
        ("/api/v1/_test/validate?value=invalid", 422, "VALIDATION_ERROR"),
        ("/api/v1/_test/crash", 500, "INTERNAL_ERROR"),
    ],
)
def test_errors_share_a_safe_response_envelope(client, caplog, path, status, code):
    caplog.set_level(logging.INFO, logger="agentradar")
    response = client.get(
        path,
        headers={"X-Request-ID": "p00-error-001", "Origin": "http://localhost:3000"},
    )

    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["request_id"] == response.headers["X-Request-ID"] == "p00-error-001"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "must-not-leak" not in response.text + caplog.text
    assert any(getattr(record, "request_id", None) == "p00-error-001" for record in caplog.records)


def test_valid_input_is_still_accepted(client):
    response = client.get("/api/v1/_test/validate?value=42")
    assert response.status_code == 200
    assert response.json() == {"value": 42}


def test_cors_preflight_exposes_request_id_and_rejects_unknown_origins(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["X-Request-ID"]

    rejected = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in rejected.headers

    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert "X-Request-ID" in allowed.headers["access-control-expose-headers"]


def test_rejected_cors_preflight_uses_the_error_envelope(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "CORS_REJECTED"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "access-control-allow-origin" not in response.headers
