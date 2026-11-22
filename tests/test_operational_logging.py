"""Privacy, fail-open, and coverage tests for plugin operational logs."""

import importlib
import json
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

import socialmedia.operational_log as operational_log
from socialmedia.operational_log import (
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    log_operation,
    logged_request,
)
from socialmedia.providers.base import _MAX_MEDIA_BYTES, _safe_fetch_url
from socialmedia.providers.bluesky import BlueskyProvider
from socialmedia.providers.telegram import TelegramProvider


@pytest.fixture
def captured(monkeypatch):
    records = []

    def fake_log(level, action, extra=None):
        records.append((level, action, extra or {}))

    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", fake_log)
    monkeypatch.setattr(operational_log, "_HOST_LOG_EVENT", None)
    return records


def test_drops_sensitive_and_unused_fields(captured):
    log_operation(
        "plugin.loaded",
        OUTCOME_SUCCESS,
        backend="bluesky",
        email="person@example.com",
        token="secret-token",
        app_password="app-password-secret",
        bot_token="12345:bot-secret",
        client_secret="oauth-client-secret",
        body="{raw}",
        event_id=12,
        user_id=34,
        object_id=56,
        job_id="job-123",
        request_id="req-456",
        route="plugins:socialmedia:posts",
        order_id=99,
        order_code="ABC123",
        payment_provider="stripe",
        webhook_id=77,
    )
    assert len(captured) == 1
    extra = captured[0][2]
    assert extra["backend"] == "bluesky"
    assert extra["event_id"] == 12
    assert extra["user_id"] == 34
    assert extra["object_id"] == 56
    assert extra["job_id"] == "job-123"
    assert extra["request_id"] == "req-456"
    assert extra["route"] == "plugins:socialmedia:posts"
    assert extra["outcome"] == "success"
    for dropped in (
        "email",
        "token",
        "app_password",
        "bot_token",
        "client_secret",
        "body",
        "order_id",
        "order_code",
        "payment_provider",
        "webhook_id",
    ):
        assert dropped not in extra
    blob = str(extra)
    assert "person@example.com" not in blob
    assert "secret-token" not in blob
    assert "app-password-secret" not in blob
    assert "bot-secret" not in blob
    assert "oauth-client-secret" not in blob


def test_allows_safe_constant_error_codes_with_token_or_secret_substrings(captured):
    for code in ("invalid_token", "token_expired", "missing_secret"):
        log_operation(
            "connection.request",
            OUTCOME_FAILURE,
            backend="linkedin",
            error_code=code,
        )
    assert [item[2]["error_code"] for item in captured] == [
        "invalid_token",
        "token_expired",
        "missing_secret",
    ]


def test_rejects_unsafe_action_and_backend(captured):
    log_operation("has space", OUTCOME_SUCCESS, backend="bluesky")
    assert captured == []
    log_operation(
        "connection.request",
        OUTCOME_FAILURE,
        backend="bad backend",
        error_code="not safe",
    )
    assert len(captured) == 1
    assert captured[0][1] == "connection.request"
    assert "backend" not in captured[0][2]
    assert "error_code" not in captured[0][2]


def test_logging_failure_is_swallowed(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("log sink down")

    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", boom)
    monkeypatch.setattr(operational_log, "_HOST_LOG_EVENT", None)
    log_operation("plugin.loaded", OUTCOME_SUCCESS, backend="bluesky")


def test_host_emitter_runtime_error_falls_back_to_logger(monkeypatch):
    records = []

    def boom(*args, **kwargs):
        raise RuntimeError("host emitter failed")

    def fake_log(level, action, extra=None):
        records.append((level, action, extra or {}))

    monkeypatch.setattr(operational_log, "_HOST_LOG_EVENT", boom)
    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", fake_log)

    log_operation("social.post", OUTCOME_SUCCESS, backend="bluesky", object_id=42)
    assert len(records) == 1
    assert records[0][1] == "social.post"
    assert records[0][2]["backend"] == "bluesky"
    assert records[0][2]["object_id"] == 42


def test_host_emitter_import_non_import_error_is_contained(monkeypatch):
    broken_module = types.ModuleType("eventyay.base.operational_logging")

    def __getattr__(name):
        raise RuntimeError("broken host module")

    broken_module.__getattr__ = __getattr__
    monkeypatch.setitem(sys.modules, "eventyay.base.operational_logging", broken_module)
    reloaded = importlib.reload(operational_log)
    try:
        assert reloaded._HOST_LOG_EVENT is None
    finally:
        monkeypatch.undo()
        importlib.reload(operational_log)


def test_logged_request_records_status_without_url(captured, monkeypatch):
    class Response:
        status_code = 201

    def fake_post(url, **kwargs):
        assert url == "https://example.invalid/secret"
        assert kwargs["json"]["token"] == "raw"
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)
    logged_request(
        "linkedin", "POST", "https://example.invalid/secret", json={"token": "raw"}
    )
    assert captured[-1][1] == "connection.request"
    extra = captured[-1][2]
    assert extra["status"] == 201
    assert extra["outcome"] == "success"
    assert "example.invalid" not in str(extra)
    assert "raw" not in str(extra)


def test_logged_request_honors_requests_request_mock(captured, monkeypatch):
    class Response:
        status_code = 200

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://example.invalid/data"
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    logged_request("twitter", "GET", "https://example.invalid/data")
    assert captured[-1][1] == "connection.request"
    assert captured[-1][2]["backend"] == "twitter"
    assert captured[-1][2]["status"] == 200


def test_safe_fetch_url_stream_logs_after_body_consumption(captured, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    resp = MagicMock()
    resp.is_redirect = False
    resp.status_code = 200
    resp.apparent_encoding = "utf-8"

    def iter_chunks(chunk_size=65536):
        # Nothing logged before stream body consumption completes
        assert captured == []
        yield b"part1-"
        assert captured == []
        yield b"part2"

    resp.iter_content.side_effect = iter_chunks
    monkeypatch.setattr(requests, "get", lambda *a, **kw: resp)

    fetched = _safe_fetch_url("https://example.com/avatar.png")
    assert fetched._content == b"part1-part2"
    assert len(captured) == 1
    extra = captured[0][2]
    assert extra["action"] == "connection.request"
    assert extra["outcome"] == "success"
    assert extra["status"] == 200
    assert "duration_ms" in extra
    assert "example.com" not in str(extra)


def test_safe_fetch_url_stream_logs_failure_when_body_read_times_out(
    captured, monkeypatch
):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    resp = MagicMock()
    resp.is_redirect = False
    resp.status_code = 200

    def iter_timeout(chunk_size=65536):
        yield b"partial"
        raise requests.Timeout("read timed out")

    resp.iter_content.side_effect = iter_timeout
    monkeypatch.setattr(requests, "get", lambda *a, **kw: resp)

    with pytest.raises(requests.Timeout):
        _safe_fetch_url("https://example.com/slow.png")

    assert len(captured) == 1
    extra = captured[0][2]
    assert extra["action"] == "connection.request"
    assert extra["outcome"] == "failure"
    assert extra["error_code"] == "timeout"
    assert extra["status"] == 200


def test_safe_fetch_url_stream_logs_failure_on_oversized_body(captured, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    resp = MagicMock()
    resp.is_redirect = False
    resp.status_code = 200
    resp.iter_content.return_value = [b"x" * (_MAX_MEDIA_BYTES + 1)]
    monkeypatch.setattr(requests, "get", lambda *a, **kw: resp)

    with pytest.raises(ValueError, match="exceeds maximum allowed size"):
        _safe_fetch_url("https://example.com/huge.png")

    assert len(captured) == 1
    assert captured[0][2]["outcome"] == "failure"
    assert captured[0][2]["error_code"] == "response_too_large"


def test_safe_fetch_url_debug_stream_logs_failure_on_content_error(
    captured, monkeypatch
):
    from django.conf import settings

    monkeypatch.setattr(settings, "DEBUG", True, raising=False)
    monkeypatch.setattr(
        "socialmedia.providers.base._try_local_media_fallback", lambda url: None
    )

    class BrokenStreamResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        @property
        def content(self):
            raise requests.ConnectionError("stream dropped")

    monkeypatch.setattr(requests, "get", lambda *a, **kw: BrokenStreamResponse())

    with pytest.raises(requests.ConnectionError):
        _safe_fetch_url("https://example.com/debug.png")

    assert len(captured) == 1
    assert captured[0][2]["outcome"] == "failure"
    assert captured[0][2]["error_code"] == "request_error"


def test_bluesky_provider_logs_without_secrets_or_text(captured, monkeypatch):
    account = SimpleNamespace(
        provider="bluesky",
        platform_username="@test.bsky.social",
        credentials={
            "handle": "test.bsky.social",
            "app_password": "bsky-app-secret-password",
            "pds_url": "https://bsky.social",
        },
    )
    provider = BlueskyProvider(account)
    monkeypatch.setattr(
        "socialmedia.providers.bluesky._validate_url_host", lambda url: None
    )

    res_session = MagicMock()
    res_session.status_code = 200
    res_session.json.return_value = {
        "accessJwt": "secret-jwt-token",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }
    res_record = MagicMock()
    res_record.status_code = 200
    res_record.json.return_value = {
        "uri": "at://did:plc:12345/app.bsky.feed.post/3l7example",
    }
    calls = iter([res_session, res_record])
    monkeypatch.setattr(requests, "post", lambda *a, **kw: next(calls))

    result = provider.publish_post("Secret post body https://eventyay.com")
    assert result["post_id"] == "3l7example"
    assert len(captured) == 2
    assert all(item[1] == "connection.request" for item in captured)
    assert all(item[2]["backend"] == "bluesky" for item in captured)
    blob = str(captured)
    assert "bsky-app-secret-password" not in blob
    assert "secret-jwt-token" not in blob
    assert "Secret post body" not in blob
    assert "bsky.social" not in blob


def test_telegram_provider_redacts_bot_token_on_network_error(captured, monkeypatch):
    account = SimpleNamespace(
        provider="telegram",
        platform_username="@mychannel",
        credentials={"bot_token": "999999:SUPERSECRETTOKEN"},
    )
    provider = TelegramProvider(account)

    def fail_post(*args, **kwargs):
        raise requests.ConnectionError(
            "HTTPSConnectionPool: Max retries for https://api.telegram.org/bot999999:SUPERSECRETTOKEN/sendMessage"
        )

    monkeypatch.setattr(requests, "post", fail_post)

    from socialmedia.providers.base import PublishingError

    with pytest.raises(PublishingError) as exc_info:
        provider.publish_post("Hello channel")

    assert "SUPERSECRETTOKEN" not in str(exc_info.value)
    assert "SUPERSECRETTOKEN" not in str(captured)
    assert captured[-1][2]["backend"] == "telegram"
    assert captured[-1][2]["outcome"] == "failure"


def test_publish_single_post_post_save_host_logger_failure(monkeypatch):
    import socialmedia.tasks as tasks_mod

    records = []

    def boom(*args, **kwargs):
        raise RuntimeError("host logger unavailable")

    def fake_log(level, action, extra=None):
        records.append((level, action, extra or {}))

    monkeypatch.setattr(operational_log, "_HOST_LOG_EVENT", boom)
    monkeypatch.setattr(logging.getLogger("eventyay.plugins"), "log", fake_log)

    saved_states = []

    class DummyPost:
        pk = 101
        post_text = "Post body"
        media_url = None
        status = "exported"
        error_message = ""

        def save(self, update_fields=None):
            saved_states.append(self.status)

    dummy_post = DummyPost()
    dummy_account = SimpleNamespace(provider="bluesky")
    dummy_provider = SimpleNamespace(
        publish_post=lambda text, media=None: {"post_id": "1", "url": ""}
    )

    monkeypatch.setattr(
        tasks_mod,
        "claim_post_for_publishing",
        lambda post_pk, provider_name: (dummy_post, dummy_account),
    )
    monkeypatch.setattr(tasks_mod, "get_provider", lambda account: dummy_provider)

    tasks_mod.publish_single_post(101, "bluesky")

    assert dummy_post.status == "published"
    assert saved_states == ["published"]
    actions = [item[1] for item in records]
    assert actions == ["job.start", "social.post", "job.finish"]
    assert records[1][2]["backend"] == "bluesky"
    assert records[1][2]["object_id"] == 101


def test_route_handlers_log_operational_outcomes_without_pii(captured, monkeypatch):
    from django.core.cache import cache

    monkeypatch.setattr(cache, "get", lambda *a, **kw: None)
    monkeypatch.setattr(cache, "set", lambda *a, **kw: None)

    import socialmedia.views as views_mod

    # 1. test_connection: unauthenticated -> auth.denied
    unauth_req = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=False),
        organizer=SimpleNamespace(pk=1, slug="org"),
        resolver_match=SimpleNamespace(
            view_name="plugins:socialmedia:organizer_account_test"
        ),
    )
    resp_unauth = views_mod.test_connection(unauth_req, "org", 1)
    assert resp_unauth.status_code == 403
    assert captured[-1][1] == "auth.denied"

    # 2. test_connection: permission denied -> permission.denied
    denied_req = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(
            is_authenticated=True,
            pk=7,
            has_organizer_permission=lambda *a, **kw: False,
        ),
        organizer=SimpleNamespace(pk=1, slug="org"),
        resolver_match=SimpleNamespace(
            view_name="plugins:socialmedia:organizer_account_test"
        ),
    )
    resp_denied = views_mod.test_connection(denied_req, "org", 1)
    assert resp_denied.status_code == 403
    assert captured[-1][1] == "permission.denied"
    assert captured[-1][2]["user_id"] == 7

    # 3. publish_post_now: mocked post & provider -> social.post success
    dummy_post = SimpleNamespace(
        pk=55,
        entity_id="cfp_1_bluesky",
        media_url="",
        post_text="Private draft text",
        status="scheduled",
        error_message="",
        save=lambda **kw: None,
    )
    dummy_account = SimpleNamespace(provider="bluesky")

    class DummyQuerySet:
        def __init__(self, obj):
            self._obj = obj

        def select_for_update(self, **kw):
            return self

        def first(self):
            return self._obj

        def __iter__(self):
            return iter([self._obj] if self._obj else [])

    monkeypatch.setattr(
        views_mod.SocialMediaPost.objects,
        "filter",
        lambda *a, **kw: DummyQuerySet(dummy_post),
    )
    monkeypatch.setattr(
        views_mod.SocialMediaAccount.objects,
        "filter",
        lambda *a, **kw: DummyQuerySet(dummy_account),
    )
    monkeypatch.setattr(views_mod.transaction, "atomic", lambda: MagicMock())
    monkeypatch.setattr(
        views_mod,
        "get_provider",
        lambda acc: SimpleNamespace(
            publish_post=lambda text, media=None: {"post_id": "1", "url": ""}
        ),
    )

    pub_req = SimpleNamespace(
        method="POST",
        body=json.dumps({"db_id": 55}).encode("utf-8"),
        user=SimpleNamespace(
            is_authenticated=True,
            pk=7,
            has_event_permission=lambda *a, **kw: True,
        ),
        organizer=SimpleNamespace(pk=1, slug="org"),
        event=SimpleNamespace(
            pk=99,
            slug="ev",
            organizer=SimpleNamespace(pk=1, slug="org"),
            get_plugins=lambda: ["socialmedia"],
        ),
        resolver_match=SimpleNamespace(view_name="plugins:socialmedia:publish_now"),
    )
    resp_pub = views_mod.publish_post_now(pub_req, "org", "ev")
    assert resp_pub.status_code == 200
    assert captured[-1][1] == "social.post"
    assert captured[-1][2]["outcome"] == "success"
    assert captured[-1][2]["backend"] == "bluesky"
    assert captured[-1][2]["event_id"] == 99
    assert captured[-1][2]["object_id"] == 55
    assert "Private draft text" not in str(captured)
