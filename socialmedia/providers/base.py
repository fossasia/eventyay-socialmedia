import ipaddress
import logging
import socket
from typing import Any

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
