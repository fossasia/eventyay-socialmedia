import ipaddress
import socket
from urllib.parse import urlparse

from .providers.base import PublishingError


def validate_safe_url(url: str) -> str:
    """Validates that a URL uses http/https scheme and does not target
    private, loopback, or cloud metadata IP addresses (SSRF prevention).
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

    # Block common local hostnames
    if hostname.lower() in ("localhost", "localhost.localdomain", "127.0.0.1", "::1"):
        raise PublishingError("Media URL points to a forbidden local address.")

    try:
        # Resolve hostname to IP addresses
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
    except socket.gaierror as e:
        raise PublishingError(
            f"Failed to resolve media URL hostname '{hostname}': {e}"
        ) from e

    return url
