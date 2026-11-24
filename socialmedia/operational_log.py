"""Privacy-safe operational logs for this plugin.

Delegates to ``eventyay.base.operational_logging.log_event`` when the host
provides it, so correlation IDs and the process-log allowlist stay shared.
Older hosts or runtime host-logger errors fall back to ``eventyay.plugins``.
Logging never raises into product code.

Emails, names, tokens, secrets, URLs, and request or response bodies are
dropped. Only opaque IDs, status codes, durations, and safe error codes are
kept.
"""

from __future__ import annotations

import functools
import logging
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

import requests
import requests.api as requests_api

try:
    from celery import current_task as _CELERY_CURRENT_TASK
except Exception:
    _CELERY_CURRENT_TASK = None

try:
    from eventyay.base.operational_logging import (
        bind_job_id as _HOST_BIND_JOB_ID,
    )
    from eventyay.base.operational_logging import (
        bind_request_id as _HOST_BIND_REQUEST_ID,
    )
    from eventyay.base.operational_logging import (
        get_job_id as _HOST_GET_JOB_ID,
    )
    from eventyay.base.operational_logging import (
        get_request_id as _HOST_GET_REQUEST_ID,
    )
    from eventyay.base.operational_logging import (
        log_event as _HOST_LOG_EVENT,
    )
    from eventyay.base.operational_logging import (
        reset_job_id as _HOST_RESET_JOB_ID,
    )
    from eventyay.base.operational_logging import (
        reset_request_id as _HOST_RESET_REQUEST_ID,
    )
except Exception:
    _HOST_LOG_EVENT = None
    _HOST_GET_REQUEST_ID = None
    _HOST_GET_JOB_ID = None
    _HOST_BIND_JOB_ID = None
    _HOST_RESET_JOB_ID = None
    _HOST_BIND_REQUEST_ID = None
    _HOST_RESET_REQUEST_ID = None

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_LOGGER = logging.getLogger("eventyay.plugins")
_INT_FIELDS = frozenset({"event_id", "user_id", "status", "duration_ms", "retry_count"})
_IDENTIFIER_FIELDS = frozenset(
    {"error_code", "backend", "job_name", "route", "request_id", "job_id"}
)
_REQUEST_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

_FALLBACK_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "socialmedia_request_id", default=None
)
_FALLBACK_JOB_ID: ContextVar[str | None] = ContextVar(
    "socialmedia_job_id", default=None
)
_JOB_FAILURE_CODE: ContextVar[str | None] = ContextVar(
    "socialmedia_job_failure_code", default=None
)


def _safe_identifier(value):
    if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return None


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    if _HOST_GET_REQUEST_ID is not None:
        try:
            val = _HOST_GET_REQUEST_ID()
            if val:
                return val
        except Exception:
            pass
    return _FALLBACK_REQUEST_ID.get()


def get_job_id() -> str | None:
    if _HOST_GET_JOB_ID is not None:
        try:
            val = _HOST_GET_JOB_ID()
            if val:
                return val
        except Exception:
            pass
    return _FALLBACK_JOB_ID.get()


def _current_celery_task_id() -> str | None:
    if _CELERY_CURRENT_TASK is None:
        return None
    try:
        req = getattr(_CELERY_CURRENT_TASK, "request", None)
        return _safe_identifier(getattr(req, "id", None))
    except Exception:
        return None


@contextmanager
def bind_request_context(request_id: str | None = None):
    """Bind a request correlation ID on host and fallback ContextVars."""
    cid = _safe_identifier(request_id) if request_id else None
    if cid is None:
        cid = new_correlation_id()
    fallback_token = _FALLBACK_REQUEST_ID.set(cid)
    prev_host = None
    bound_host = False
    if _HOST_BIND_REQUEST_ID is not None and _HOST_RESET_REQUEST_ID is not None:
        try:
            prev_host = _HOST_GET_REQUEST_ID() if _HOST_GET_REQUEST_ID else None
            _HOST_BIND_REQUEST_ID(cid)
            bound_host = True
        except Exception:
            bound_host = False
    try:
        yield cid
    finally:
        _FALLBACK_REQUEST_ID.reset(fallback_token)
        if bound_host:
            try:
                if prev_host:
                    _HOST_BIND_REQUEST_ID(prev_host)
                else:
                    _HOST_RESET_REQUEST_ID()
            except Exception:
                pass


@contextmanager
def bind_job_context(job_id: str | None = None):
    """Bind a job correlation ID on host and fallback ContextVars."""
    cid = _safe_identifier(job_id) if job_id else None
    if cid is None:
        cid = _current_celery_task_id() or new_correlation_id()
    fallback_token = _FALLBACK_JOB_ID.set(cid)
    prev_host = None
    bound_host = False
    if _HOST_BIND_JOB_ID is not None and _HOST_RESET_JOB_ID is not None:
        try:
            prev_host = _HOST_GET_JOB_ID() if _HOST_GET_JOB_ID else None
            _HOST_BIND_JOB_ID(cid)
            bound_host = True
        except Exception:
            bound_host = False
    try:
        yield cid
    finally:
        _FALLBACK_JOB_ID.reset(fallback_token)
        if bound_host:
            try:
                if prev_host:
                    _HOST_BIND_JOB_ID(prev_host)
                else:
                    _HOST_RESET_JOB_ID()
            except Exception:
                pass


def mark_job_failed(error_code: str = "task_failed") -> None:
    """Signal to an enclosing ``traced_job`` that the job ended in failure."""
    cleaned = _safe_identifier(error_code) or "task_failed"
    _JOB_FAILURE_CODE.set(cleaned)


def _clean(fields):
    extra = {}
    for key, value in fields.items():
        if value is None or value == "":
            continue
        if key in _INT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            extra[key] = value
            continue
        if key in _IDENTIFIER_FIELDS:
            cleaned = _safe_identifier(value if isinstance(value, str) else None)
            if cleaned is not None:
                extra[key] = cleaned
            continue
        if key == "object_id":
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                extra[key] = value
            else:
                cleaned = _safe_identifier(str(value))
                if cleaned is not None:
                    extra[key] = cleaned
    return extra


def log_operation(action, outcome, **fields):
    """Emit one allowlisted operational line. Failures are swallowed."""
    try:
        if not isinstance(action, str) or _safe_identifier(action) is None:
            return
        if outcome not in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
            outcome = OUTCOME_FAILURE
        level = logging.WARNING if outcome == OUTCOME_FAILURE else logging.INFO
        payload = _clean(fields)
        if _HOST_LOG_EVENT is not None:
            try:
                _HOST_LOG_EVENT("plugins", action, outcome, level=level, **payload)
                return
            except Exception:
                pass
        if "request_id" not in payload:
            req_id = _safe_identifier(get_request_id())
            if req_id is not None:
                payload["request_id"] = req_id
        if "job_id" not in payload:
            j_id = _safe_identifier(get_job_id())
            if j_id is not None:
                payload["job_id"] = j_id
        extra = {
            "component": "plugins",
            "outcome": outcome,
            "action": action,
            **payload,
        }
        _LOGGER.log(level, action, extra=extra)
    except Exception:
        return


def log_plugin_loaded(backend):
    log_operation("plugin.loaded", OUTCOME_SUCCESS, backend=backend)


def _elapsed_ms(started):
    return int((time.monotonic() - started) * 1000)


def log_request_outcome(
    backend,
    started,
    *,
    response=None,
    error_code=None,
    ok_statuses=(),
    retry_count=0,
):
    """Emit ``connection.request`` using ``started`` monotonic timestamp."""
    status = getattr(response, "status_code", None)
    status_ok = isinstance(status, int) and not isinstance(status, bool)
    safe_retries = (
        retry_count
        if isinstance(retry_count, int)
        and not isinstance(retry_count, bool)
        and retry_count >= 0
        else None
    )
    if error_code is not None:
        log_operation(
            "connection.request",
            OUTCOME_FAILURE,
            backend=backend,
            status=status if status_ok else None,
            duration_ms=_elapsed_ms(started),
            retry_count=safe_retries,
            error_code=error_code,
        )
        return
    tolerated = status_ok and status in set(ok_statuses)
    failed = status_ok and status >= 400 and not tolerated
    log_operation(
        "connection.request",
        OUTCOME_FAILURE if failed else OUTCOME_SUCCESS,
        backend=backend,
        status=status if status_ok else None,
        duration_ms=_elapsed_ms(started),
        retry_count=safe_retries,
        error_code="http_error" if failed else None,
    )


@contextmanager
def logged_stream_outcome(backend, started, response, retry_count=0):
    """Record ``connection.request`` after streaming body consumption completes."""
    try:
        yield
    except requests.Timeout:
        log_request_outcome(
            backend,
            started,
            response=response,
            error_code="timeout",
            retry_count=retry_count,
        )
        raise
    except requests.HTTPError:
        log_request_outcome(
            backend, started, response=response, retry_count=retry_count
        )
        raise
    except requests.RequestException:
        log_request_outcome(
            backend,
            started,
            response=response,
            error_code="request_error",
            retry_count=retry_count,
        )
        raise
    except ValueError:
        log_request_outcome(
            backend,
            started,
            response=response,
            error_code="response_too_large",
            retry_count=retry_count,
        )
        raise
    except Exception:
        log_request_outcome(
            backend,
            started,
            response=response,
            error_code="stream_error",
            retry_count=retry_count,
        )
        raise
    else:
        log_request_outcome(
            backend, started, response=response, retry_count=retry_count
        )


def _send_request(method, url, **kwargs):
    """Call requests without changing mocks or redirect defaults.

    A patched ``requests.get`` or ``requests.post`` wins. Otherwise a patched
    ``requests.request`` wins. Unpatched calls use the verb helper.
    """
    verb_name = str(method).lower()
    if verb_name in _REQUEST_VERBS:
        patched = getattr(requests, verb_name, None)
        real = getattr(requests_api, verb_name, None)
        if patched is not None and patched is not real:
            return patched(url, **kwargs)  # codeql[py/full-ssrf]
    if requests.request is not requests_api.request:
        return requests.request(method, url, **kwargs)  # codeql[py/full-ssrf]
    if verb_name in _REQUEST_VERBS:
        real = getattr(requests_api, verb_name)
        return real(url, **kwargs)  # codeql[py/full-ssrf]
    return requests_api.request(method, url, **kwargs)  # codeql[py/full-ssrf]


def logged_request(backend, method, url, **kwargs):
    """Log status, duration, and retry count for one HTTP call.

    ``ok_statuses`` and ``retry_count`` are not sent to the server. Use
    ``ok_statuses`` when the caller already treats a 4xx response as success.
    When ``defer_log=True`` is passed (for ``stream=True`` calls whose body is
    consumed incrementally by the caller), immediate send failures are still
    logged and the caller logs the final transfer outcome via
    ``logged_stream_outcome`` or ``log_request_outcome``.
    The same exception is re-raised. The URL and body are not logged.
    """
    ok_statuses = kwargs.pop("ok_statuses", ())
    defer_log = kwargs.pop("defer_log", False)
    started = kwargs.pop("started", None)
    retry_count = kwargs.pop("retry_count", 0)
    if started is None:
        started = time.monotonic()
    try:
        response = _send_request(method, url, **kwargs)
    except requests.Timeout:
        log_request_outcome(
            backend, started, error_code="timeout", retry_count=retry_count
        )
        raise
    except requests.RequestException:
        log_request_outcome(
            backend, started, error_code="request_error", retry_count=retry_count
        )
        raise
    if not defer_log:
        log_request_outcome(
            backend,
            started,
            response=response,
            ok_statuses=ok_statuses,
            retry_count=retry_count,
        )
    return response


def traced_job(job_name):
    """Log job boundaries with a fresh per-execution correlation ID."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with bind_job_context(kwargs.get("job_id")):
                failure_token = _JOB_FAILURE_CODE.set(None)
                try:
                    log_operation("job.start", OUTCOME_SUCCESS, job_name=job_name)
                    try:
                        result = fn(*args, **kwargs)
                    except Exception as exc:
                        retried = type(exc).__name__ == "Retry"
                        log_operation(
                            "job.retry" if retried else "job.fail",
                            OUTCOME_FAILURE,
                            job_name=job_name,
                            error_code="retry" if retried else type(exc).__name__,
                        )
                        raise
                    failure_code = _JOB_FAILURE_CODE.get()
                    if failure_code is not None:
                        log_operation(
                            "job.fail",
                            OUTCOME_FAILURE,
                            job_name=job_name,
                            error_code=failure_code,
                        )
                    else:
                        log_operation("job.finish", OUTCOME_SUCCESS, job_name=job_name)
                    return result
                finally:
                    _JOB_FAILURE_CODE.reset(failure_token)

        return wrapper

    return decorator
