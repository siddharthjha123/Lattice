"""Optional bounded DNS lookup; retain libpq's hostname for verified TLS."""

import logging
from ipaddress import ip_address

import dns.exception
import dns.resolver

LOGGER = logging.getLogger(__name__)


def resolve_connection_address(parameters):
    host = parameters.get("host")
    if not host or host == "localhost" or host.startswith("/"):
        return None
    if "," in host:
        raise ValueError(
            "Direct DNS supports one database hostname; use native resolution for multi-host URLs"
        )
    try:
        ip_address(host)
        return None
    except ValueError:
        pass
    try:
        answers = dns.resolver.resolve(host, "A", lifetime=3, search=False)
    except (dns.exception.Timeout, dns.resolver.NoNameservers, OSError) as error:
        # macOS native resolution can use its cache/scoped resolver even when
        # direct port-53 requests time out. Returning None leaves libpq to
        # resolve the original hostname; verified TLS settings stay intact.
        LOGGER.warning(
            "Direct database DNS unavailable (%s); using native hostname resolution",
            type(error).__name__,
        )
        return None
    if not answers:
        raise ConnectionError("Database DNS returned no IPv4 address")
    return str(ip_address(answers[0].address))
