import ipaddress
import logging
import mimetypes
import os
import socket
from urllib.parse import urlparse

import requests

from .providers.base import PublishingError

logger = logging.getLogger(__name__)


def _is_debug() -> bool:
    """Return True if Django DEBUG mode is active."""
    try:
        from django.conf import settings
        return bool(getattr(settings, "DEBUG", False))
    except Exception:
        return False


def _try_local_media_fallback(url: str) -> tuple[bytes, str] | None:
    """Read a media URL from MEDIA_ROOT when it points to our own server.

    Used when the URL maps to a local Django-served file
    (e.g. ``http://localhost:8000/media/avatars/foo.jpg``).
    Applies a realpath + MEDIA_ROOT prefix guard to prevent path traversal.

    Returns:
        ``(content_bytes, mime_type)`` on success, or ``None`` if unmappable.
    """
    try:
        from django.conf import settings
    except Exception:
        return None

    media_root = getattr(settings, "MEDIA_ROOT", None)
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if not media_root:
        return None

    path = urlparse(url).path  # e.g. /media/avatars/foo.jpg
    if not path.startswith(media_url):
        return None

    rel = path[len(media_url):]  # e.g. avatars/foo.jpg
    candidate = os.path.join(media_root, rel)
    real_candidate = os.path.realpath(candidate)
    real_root = os.path.realpath(media_root)

    if not real_candidate.startswith(real_root + os.sep) and real_candidate != real_root:
        logger.warning("_try_local_media_fallback: %r escapes MEDIA_ROOT, skipping.", url)
        return None

    if not os.path.isfile(real_candidate):
        logger.debug("_try_local_media_fallback: file not found at %r", real_candidate)
        return None

    mime_type, _ = mimetypes.guess_type(real_candidate)
    try:
        with open(real_candidate, "rb") as f:
            content = f.read()
    except OSError as exc:
        logger.debug("_try_local_media_fallback: cannot read %r: %s", real_candidate, exc)
        return None

    logger.debug(
        "_try_local_media_fallback: served %r from disk (%d bytes)", url, len(content)
    )
    return content, mime_type or "image/jpeg"


class DNSResolverContext:
    """Context manager that pins socket.getaddrinfo to resolve a specific hostname
    strictly to a pre-validated IP address during HTTP requests.
    Prevents Time of Check to Time of Use (TOCTOU) DNS Rebinding SSRF attacks.
    """

    def __init__(self, hostname: str, target_ip: str):
        self.hostname = hostname.lower()
        self.target_ip = target_ip
        self.orig_getaddrinfo = socket.getaddrinfo

    def __enter__(self):
        def patched_getaddrinfo(host, port, *args, **kwargs):
            if host and isinstance(host, str) and host.lower() == self.hostname:
                return self.orig_getaddrinfo(self.target_ip, port, *args, **kwargs)
            return self.orig_getaddrinfo(host, port, *args, **kwargs)

        socket.getaddrinfo = patched_getaddrinfo
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        socket.getaddrinfo = self.orig_getaddrinfo


def validate_safe_url(url: str) -> tuple[str, str]:
    """Validate that a URL uses http/https and does not target private/loopback IPs.

    In DEBUG mode, localhost is allowed — developers test against local servers.
    Returns (url, first_valid_ip_or_hostname).
    """
    if not url or not isinstance(url, str):
        raise PublishingError("Invalid media URL provided.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PublishingError(
            f"Unsupported scheme in media URL: '{parsed.scheme}'. "
            "Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise PublishingError("Invalid media URL: missing hostname.")

    # In DEBUG mode skip IP blocking — local dev servers resolve to loopback.
    if _is_debug():
        logger.debug("validate_safe_url: DEBUG mode, skipping IP block for %r", url)
        return url, hostname

    # Block common local hostnames in production.
    if hostname.lower() in ("localhost", "localhost.localdomain", "127.0.0.1", "::1"):
        raise PublishingError("Media URL points to a forbidden local address.")

    first_ip = None
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
        for res in resolved_ips:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise PublishingError(
                    f"Media URL host '{hostname}' resolved to forbidden IP '{ip}'."
                )
            if not first_ip:
                first_ip = ip_str
    except socket.gaierror as e:
        raise PublishingError(
            f"Failed to resolve media URL hostname '{hostname}': {e}"
        ) from e

    return url, first_ip or hostname


def safe_fetch_url(url: str, timeout: int = 20) -> requests.Response:
    """Safely fetch a remote URL with SSRF validation and DNS pinning.

    In DEBUG mode, own-server URLs (under MEDIA_URL) are served directly
    from MEDIA_ROOT instead of making an HTTP request back to localhost.
    """
    if _is_debug():
        local = _try_local_media_fallback(url)
        if local is not None:
            content, mime_type = local
            resp = requests.Response()
            resp.status_code = 200
            resp._content = content
            resp.headers["Content-Type"] = mime_type
            return resp

    url, safe_ip = validate_safe_url(url)
    hostname = urlparse(url).hostname

    with DNSResolverContext(hostname, safe_ip):
        return requests.get(url, timeout=timeout)

