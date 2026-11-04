"""Bounded HTTPS DNS with TTL caching; libpq retains the verified TLS hostname."""

import logging
import threading
import time
from collections import OrderedDict
from ipaddress import ip_address

import dns.message
import dns.rcode
import dns.rdatatype
import httpx

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://1.1.1.1/dns-query"


def lookup_ipv4(host):
    query = dns.message.make_query(host, "A")
    with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
        response = client.post(
            ENDPOINT,
            content=query.to_wire(),
            headers={
                "Accept": "application/dns-message",
                "Content-Type": "application/dns-message",
            },
        )
        response.raise_for_status()
        if (
            response.headers.get("content-type", "").split(";", 1)[0]
            != "application/dns-message"
            or len(response.content) > 65535
        ):
            raise ValueError("Invalid encrypted DNS response")
        answer = dns.message.from_wire(response.content)
    if not query.is_response(answer) or answer.rcode() != dns.rcode.NOERROR:
        raise ValueError("Encrypted DNS query was not answered")
    # Include CNAME TTLs so an alias change cannot outlive its DNS validity.
    ttls = [record.ttl for record in answer.answer]
    for record in answer.answer:
        if record.rdtype == dns.rdatatype.A and len(record):
            return str(ip_address(record[0].address)), min(ttls)
    raise ValueError("Encrypted DNS returned no IPv4 address")


class EncryptedResolver:
    def __init__(self, lookup=None, clock=None):
        self.lookup = lookup or lookup_ipv4
        self.clock = clock or time.monotonic
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def resolve(self, parameters):
        host = parameters.get("host")
        if not host or host == "localhost" or host.startswith("/"):
            return None
        if "," in host:
            raise ValueError("Encrypted DNS requires one database hostname")
        try:
            ip_address(host)
            return None
        except ValueError:
            pass
        # Serialize cache misses for the one service host: simultaneous joins
        # share a lookup rather than issuing one query per database connection.
        with self.lock:
            entry = self.cache.get(host)
            if entry is not None and self.clock() < entry[1]:
                self.cache.move_to_end(host)
                return entry[0]
            self.cache.pop(host, None)
            try:
                address, ttl = self.lookup(host)
                address = ip_address(address)
                if address.version != 4 or ttl < 0:
                    raise ValueError("Invalid encrypted DNS address or TTL")
            except Exception as error:  # noqa: BLE001 -- do not expose the private hostname or response
                LOGGER.warning(
                    "Encrypted database DNS unavailable (%s)", type(error).__name__
                )
                raise ConnectionError("Encrypted database DNS unavailable") from None
            address = str(address)
            if ttl:
                self.cache[host] = (address, self.clock() + min(ttl, 300))
                if len(self.cache) > 64:
                    self.cache.popitem(last=False)
            return address
