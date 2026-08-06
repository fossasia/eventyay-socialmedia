import ipaddress
import socket
from urllib.parse import urlparse

import requests

from .providers.base import PublishingError


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
    """Validates that a URL uses http/https scheme and does not target
    private, loopback, or cloud metadata IP addresses (SSRF prevention).
    Returns (url, first_valid_ip).
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

    first_ip = None
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
            if not first_ip:
                first_ip = ip_str
    except socket.gaierror as e:
        raise PublishingError(
            f"Failed to resolve media URL hostname '{hostname}': {e}"
        ) from e

    return url, first_ip or hostname


def safe_fetch_url(url: str, timeout: int = 20) -> requests.Response:
    """Safely fetches a remote URL with SSRF validation and DNS pinning
    to prevent DNS Rebinding (TOCTOU) attacks.
    """
    url, safe_ip = validate_safe_url(url)
    hostname = urlparse(url).hostname

    with DNSResolverContext(hostname, safe_ip):
        return requests.get(url, timeout=timeout)
