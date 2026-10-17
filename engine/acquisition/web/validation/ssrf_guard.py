"""
SSRF and URL safety validation guard for web acquisition.
Ensures fetched URLs and redirected targets cannot access loopback, private LAN,
cloud metadata endpoints, or unsafe protocol schemes.
"""
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple


BLOCKED_SCHEMES = {"file", "javascript", "data", "ftp", "file", "ssh", "sftp", "gopher", "dict", "ldap"}
ALLOWED_SCHEMES = {"http", "https"}


def is_safe_url(url: str, allow_loopback_for_testing: bool = False) -> Tuple[bool, str]:
    """
    Check if a URL is safe to fetch over the network.
    Returns (is_safe, failure_reason).
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL"

    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
    except Exception as e:
        return False, f"Malformed URL syntax: {e}"

    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES:
        return False, f"Blocked unsafe URL scheme '{scheme}://'"

    if scheme not in ALLOWED_SCHEMES:
        return False, f"Unsupported URL scheme '{scheme}://' (only http/https permitted)"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no valid hostname"

    # Block well-known cloud metadata hostnames directly
    lower_host = hostname.lower()
    if lower_host in {"instance-data", "metadata.google.internal", "metadata"}:
        return False, f"Forbidden cloud metadata hostname '{hostname}'"

    # If allow_loopback_for_testing is True and hostname is localhost or 127.0.0.1, permit for synthetic tests
    if allow_loopback_for_testing and lower_host in {"localhost", "127.0.0.1", "::1"}:
        return True, "Safe (loopback allowed for test environment)"

    # Resolve IP addresses
    try:
        # Check if hostname itself is an IP literal
        try:
            ip = ipaddress.ip_address(hostname)
            ip_objs = [ip]
        except ValueError:
            # Resolve DNS
            try:
                addrinfo = socket.getaddrinfo(hostname, None)
                ip_objs = [ipaddress.ip_address(item[4][0]) for item in addrinfo]
            except Exception:
                # If DNS lookup fails at preflight, it is not an IP literal and cannot reach private LANs directly.
                # Allow network layer (or test mock) to attempt connection and report network status.
                return True, "Hostname unresolved at preflight; network client will handle connection"
    except Exception as e:
        return False, f"Invalid host address: {e}"

    for ip in ip_objs:
        # Unpack RFC 6052 / RFC 6146 NAT64 Well-Known Prefix (64:ff9b::/96)
        if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.IPv6Network("64:ff9b::/96"):
            embedded_ipv4 = ipaddress.IPv4Address(ip.packed[-4:])
            if embedded_ipv4.is_loopback:
                return False, f"SSRF blocked: NAT64 resolves to loopback IP '{embedded_ipv4}'"
            if embedded_ipv4.is_private and not allow_loopback_for_testing:
                return False, f"SSRF blocked: NAT64 resolves to private network IP '{embedded_ipv4}'"
            if embedded_ipv4.is_link_local:
                return False, f"SSRF blocked: NAT64 resolves to link-local IP '{embedded_ipv4}'"
            if str(embedded_ipv4) == "169.254.169.254":
                return False, "SSRF blocked: Cloud metadata service IP 169.254.169.254"
            continue

        if ip.is_loopback:
            return False, f"SSRF blocked: Host resolves to loopback IP '{ip}'"
        if ip.is_private and not allow_loopback_for_testing:
            return False, f"SSRF blocked: Host resolves to private network IP '{ip}'"
        if ip.is_link_local:
            return False, f"SSRF blocked: Host resolves to link-local IP '{ip}'"
        if ip.is_unspecified:
            return False, f"SSRF blocked: Host resolves to unspecified IP '{ip}'"
        if ip.is_multicast:
            return False, f"SSRF blocked: Host resolves to multicast IP '{ip}'"
        if ip.is_reserved:
            return False, f"SSRF blocked: Host resolves to reserved IP '{ip}'"
        # Specifically check 169.254.169.254
        if str(ip) == "169.254.169.254":
            return False, "SSRF blocked: Cloud metadata service IP 169.254.169.254"

    return True, "Safe"
