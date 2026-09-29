"""Privacy and fail-open behavior of plugin operational logs."""

import logging

import pytest

from socialmedia.operational_log import (
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    log_operation,
    logged_request,
)


@pytest.fixture
def captured(monkeypatch):
    records = []

    def fake_log(level, action, extra=None):
        records.append((level, action, extra or {}))

    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", fake_log)
    # Force the fallback logger even when the host package is installed.
    import builtins

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "eventyay.base.operational_logging" or (
            name == "eventyay.base" and fromlist and "operational_logging" in fromlist
        ):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    return records


def test_drops_email_token_and_unknown_fields(captured):
    log_operation(
        "plugin.loaded",
        OUTCOME_SUCCESS,
        backend="paypal",
        email="person@example.com",
        token="secret-token",
        body="{raw}",
        event_id=12,
    )
    assert len(captured) == 1
    extra = captured[0][2]
    assert extra["backend"] == "paypal"
    assert extra["event_id"] == 12
    assert extra["outcome"] == "success"
    assert "email" not in extra
    assert "token" not in extra
    assert "body" not in extra
    blob = str(extra)
    assert "person@example.com" not in blob
    assert "secret-token" not in blob


def test_rejects_unsafe_action_and_backend(captured):
    log_operation("has space", OUTCOME_SUCCESS, backend="paypal")
    log_operation(
        "connection.request", OUTCOME_FAILURE, backend="pay pal", error_code="not safe"
    )
    assert captured == [] or "pay pal" not in str(captured)
    assert all("pay pal" not in str(item) for item in captured)
    assert all(item[1] != "has space" for item in captured)


def test_logging_failure_is_swallowed(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("log sink down")

    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", boom)
    import builtins

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if "operational_logging" in name or (
            fromlist and "operational_logging" in fromlist
        ):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    log_operation("plugin.loaded", OUTCOME_SUCCESS, backend="paypal")


def test_logged_request_records_status_without_url(captured, monkeypatch):
    class Response:
        status_code = 201

    def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url == "https://example.invalid/secret"
        assert kwargs["json"]["token"] == "raw"
        return Response()

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    logged_request(
        "paypal", "POST", "https://example.invalid/secret", json={"token": "raw"}
    )
    assert captured[-1][1] == "connection.request"
    extra = captured[-1][2]
    assert extra["status"] == 201
    assert extra["outcome"] == "success"
    assert "example.invalid" not in str(extra)
    assert "raw" not in str(extra)
