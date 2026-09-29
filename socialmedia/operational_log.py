"""Privacy-safe operational logs for this plugin.

Delegates to ``eventyay.base.operational_logging.log_event`` when the host
provides it, so correlation IDs and the process-log allowlist stay shared.
Older hosts fall back to the ``eventyay.plugins`` logger. Logging never
raises into product code.

Emails, names, tokens, secrets, and request or response bodies are dropped.
Only opaque IDs, status codes, durations, and safe error codes are kept.

Sample lines::

    INFO eventyay.plugins: connection.request component=plugins outcome=success action=connection.request backend=paypal status=201 duration_ms=84 payment_provider=paypal
    WARNING eventyay.plugins: webhook.inbound component=plugins outcome=failure action=webhook.inbound backend=stripe error_code=signature_invalid status=400
"""

from __future__ import annotations

import functools
import logging
import re
import time

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_LOGGER = logging.getLogger("eventyay.plugins")
_INT_FIELDS = frozenset(
    {
        "event_id",
        "order_id",
        "user_id",
        "status",
        "duration_ms",
        "retry_count",
        "webhook_id",
        "recipient_count",
    }
)
_IDENTIFIER_FIELDS = frozenset(
    {
        "error_code",
        "backend",
        "job_name",
        "payment_provider",
        "model",
        "order_code",
    }
)


def _safe_identifier(value):
    if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return None


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
            if cleaned is None and isinstance(value, str):
                continue
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
    if not isinstance(action, str) or _safe_identifier(action) is None:
        return
    if outcome not in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
        outcome = OUTCOME_FAILURE
    level = logging.WARNING if outcome == OUTCOME_FAILURE else logging.INFO
    payload = _clean(fields)
    emitter = None
    try:
        from eventyay.base.operational_logging import log_event as emitter
    except ImportError:
        emitter = None
    if emitter is not None:
        try:
            emitter("plugins", action, outcome, level=level, **payload)
            return
        except Exception:
            return
    extra = {"component": "plugins", "outcome": outcome, "action": action, **payload}
    try:
        _LOGGER.log(level, action, extra=extra)
    except Exception:
        return


def log_plugin_loaded(backend):
    log_operation("plugin.loaded", OUTCOME_SUCCESS, backend=backend)


def _elapsed_ms(started):
    return int((time.monotonic() - started) * 1000)


def logged_request(backend, method, url, **kwargs):
    """``requests.request`` plus status and duration. Same exceptions, no URL or body."""
    import requests

    started = time.monotonic()
    try:
        response = requests.request(method, url, **kwargs)
    except requests.Timeout:
        log_operation(
            "connection.request",
            OUTCOME_FAILURE,
            backend=backend,
            error_code="timeout",
            duration_ms=_elapsed_ms(started),
        )
        raise
    except requests.RequestException:
        log_operation(
            "connection.request",
            OUTCOME_FAILURE,
            backend=backend,
            error_code="request_error",
            duration_ms=_elapsed_ms(started),
        )
        raise
    status = getattr(response, "status_code", None)
    failed = isinstance(status, int) and not isinstance(status, bool) and status >= 400
    log_operation(
        "connection.request",
        OUTCOME_FAILURE if failed else OUTCOME_SUCCESS,
        backend=backend,
        status=status
        if isinstance(status, int) and not isinstance(status, bool)
        else None,
        duration_ms=_elapsed_ms(started),
        error_code="http_error" if failed else None,
    )
    return response


def traced_job(job_name):
    """Log job start, finish, retry, and fail without changing the return or exception."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
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
            log_operation("job.finish", OUTCOME_SUCCESS, job_name=job_name)
            return result

        return wrapper

    return decorator
