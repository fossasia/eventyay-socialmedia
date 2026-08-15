import ipaddress
import logging
import mimetypes
import os
import socket
from typing import Any
from urllib.parse import urlparse

import requests

from socialmedia.models import SocialMediaAccount

logger = logging.getLogger(__name__)

_MAX_MEDIA_BYTES = 10 * 1024 * 1024  # 10 MB

# Private / link-local / loopback networks that should never be fetched.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("10.0.0.0/8"),     # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918
    ipaddress.ip_network("192.168.0.0/16"), # RFC1918
    ipaddress.ip_network("169.254.0.0/16"), # link-local (IMDS)
    ipaddress.ip_network("::1/128"),        # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),       # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),      # IPv6 link-local
]


def _safe_fetch_url(url: str, timeout: int = 20) -> requests.Response:
    """Fetch *url* after verifying it does not point to a private/internal host.

    Raises:
        ValueError: If the resolved IP is in a blocked range or response too large.
        requests.RequestException: On network errors.
    """
    parsed = requests.utils.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Cannot resolve hostname from URL: {url}")

    try:
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {hostname!r}: {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(
                    f"Refusing to fetch {url!r}: resolved IP {ip_str} is in "
                    f"blocked network {network}."
                )

    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()

    # Read up to _MAX_MEDIA_BYTES; reject oversized responses.
    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > _MAX_MEDIA_BYTES:
            resp.close()
            raise ValueError(
                f"Response from {url!r} exceeds maximum allowed size "
                f"({_MAX_MEDIA_BYTES // (1024 * 1024)} MB)."
            )
        chunks.append(chunk)

    resp._content = b"".join(chunks)
    resp.encoding = resp.apparent_encoding
    return resp


def _try_local_media_fallback(url: str) -> tuple[bytes, str] | None:
    """Try to serve a media URL by reading the file directly from MEDIA_ROOT.

    Used when the SSRF guard blocks a URL that points to our own server
    (e.g. ``http://localhost:8000/media/avatars/foo.jpg`` in development, or
    ``https://example.com/media/avatars/foo.jpg`` in production when the worker
    and web server share the same filesystem).

    The URL path is mapped to a filesystem path by stripping ``MEDIA_URL`` and
    joining with ``MEDIA_ROOT``. A ``realpath`` + prefix check prevents path
    traversal.

    Returns:
        ``(content_bytes, mime_type)`` on success, or ``None`` if the file
        cannot be resolved or is outside MEDIA_ROOT.
    """
    try:
        from django.conf import settings
    except Exception:
        return None

    media_root = getattr(settings, "MEDIA_ROOT", None)
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if not media_root:
        return None

    parsed = urlparse(url)
    path = parsed.path  # e.g. /media/avatars/foo.jpg

    # Strip MEDIA_URL prefix to get the relative path within MEDIA_ROOT.
    if not path.startswith(media_url):
        return None
    rel = path[len(media_url):]  # e.g. avatars/foo.jpg

    candidate = os.path.join(media_root, rel)
    real_candidate = os.path.realpath(candidate)
    real_root = os.path.realpath(media_root)

    # Reject traversal outside MEDIA_ROOT.
    if not real_candidate.startswith(real_root + os.sep) and real_candidate != real_root:
        logger.warning(
            "_try_local_media_fallback: %r resolves outside MEDIA_ROOT, skipping.",
            url,
        )
        return None

    if not os.path.isfile(real_candidate):
        logger.debug("_try_local_media_fallback: file not found at %r", real_candidate)
        return None

    mime_type, _ = mimetypes.guess_type(real_candidate)
    try:
        with open(real_candidate, "rb") as f:
            content = f.read()
    except OSError as exc:
        logger.debug("_try_local_media_fallback: could not read %r: %s", real_candidate, exc)
        return None

    logger.debug(
        "_try_local_media_fallback: served %r from local disk (%d bytes)", url, len(content)
    )
    return content, mime_type or "image/jpeg"



class PublishingError(Exception):
    """Custom exception raised when post publishing or API sync fails."""

    pass


class BaseSocialProvider:
    """Abstract base class representing a social media or scheduling provider
    integration.
    """

    def __init__(self, account: SocialMediaAccount):
        self.account = account
        self.credentials = account.credentials

    def validate_credentials(self) -> bool:
        """Verify the connection status with the remote platform or aggregator API.

        Returns:
            bool: True if connection is valid, False otherwise.
        """
        raise NotImplementedError(
            "validate_credentials must be implemented by subclasses."
        )

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        """Send text copy and media attachments to the provider API.

        Returns:
            Dict[str, Any]: A dict containing 'post_id' and 'url' of the published post.

        Raises:
            PublishingError: If the remote API returns an error or connection fails.
        """
        raise NotImplementedError("publish_post must be implemented by subclasses.")

    def send_test_message(self) -> dict[str, Any]:
        """Send a test message to verify the connection is working.

        Returns:
            Dict[str, Any]: A dict with 'success' (bool) and 'message' (str).

        Raises:
            PublishingError: If the test message fails.
        """
        raise NotImplementedError(
            "send_test_message must be implemented by subclasses."
        )

    def sync_campaign(self, posts: list[Any]) -> list[Any]:
        """(Optional override for schedulers) Batches multiple scheduled posts
        and sends them to the scheduling queue in a single sync session.
        """
        return []

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        """Return a list of step-by-step setup instructions for the provider."""
        return []
