"""DNS failure/recovery and concurrent connection lookups stay TLS-safe."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import dns.message
import dns.rrset
import httpx
import pytest

from control_plane.database.encrypted_resolution import EncryptedResolver, lookup_ipv4
from control_plane.database.session import Database


def test_encrypted_cache_expires_and_preserves_original_tls_parameters():
    clock = [0]
    lookup = Mock(side_effect=[("192.0.2.1", 10), ("192.0.2.2", 20)])
    resolver = EncryptedResolver(lookup=lookup, clock=lambda: clock[0])
    parameters = {
        "host": "database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
    }
    before = parameters.copy()
    assert resolver.resolve(parameters) == "192.0.2.1"
    clock[0] = 9
    assert resolver.resolve(parameters) == "192.0.2.1"
    assert lookup.call_count == 1
    clock[0] = 10
    assert resolver.resolve(parameters) == "192.0.2.2"
    assert lookup.call_count == 2
    assert parameters == before


def test_concurrent_connections_share_one_lookup():
    lookup = Mock(return_value=("192.0.2.1", 30))
    resolver = EncryptedResolver(lookup=lookup)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert (
            list(
                pool.map(
                    lambda _: resolver.resolve({"host": "database.example"}), range(8)
                )
            )
            == ["192.0.2.1"] * 8
        )
    lookup.assert_called_once()


def test_failed_refresh_never_reuses_expired_address_or_logs_hostname(caplog):
    clock = [0]
    resolver = EncryptedResolver(
        lookup=Mock(side_effect=[("192.0.2.1", 1), OSError("private-db-hostname")]),
        clock=lambda: clock[0],
    )
    assert resolver.resolve({"host": "database.example"}) == "192.0.2.1"
    clock[0] = 2
    with pytest.raises(ConnectionError, match="Encrypted database DNS unavailable"):
        resolver.resolve({"host": "database.example"})
    assert not resolver.cache
    assert (
        "private-db-hostname" not in caplog.text
        and "database.example" not in caplog.text
    )


def test_dns_wire_response_and_alias_ttl_are_validated(monkeypatch):
    def handle(request):
        query = dns.message.from_wire(request.content)
        answer = dns.message.make_response(query)
        answer.answer.append(
            dns.rrset.from_text(
                "database.example.", 5, "IN", "CNAME", "target.example."
            )
        )
        answer.answer.append(
            dns.rrset.from_text("target.example.", 60, "IN", "A", "192.0.2.1")
        )
        return httpx.Response(
            200,
            content=answer.to_wire(),
            headers={"content-type": "application/dns-message"},
        )

    factory = httpx.Client

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return factory(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(
        "control_plane.database.encrypted_resolution.httpx.Client", client
    )
    assert lookup_ipv4("database.example") == ("192.0.2.1", 5)


def test_connection_hook_sets_only_hostaddr(monkeypatch):
    monkeypatch.setattr(
        "control_plane.database.encrypted_resolution.lookup_ipv4",
        lambda host: ("192.0.2.1", 60),
    )
    database = Database(
        "postgresql+psycopg://user@database.example/test", encrypted_dns=True
    )
    parameters = {
        "host": "database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
        "hostaddr": "192.0.2.99",
    }
    try:
        for callback in database.engine.dialect.dispatch.do_connect:
            callback(database.engine.dialect, None, [], parameters)
        assert parameters == {
            "host": "database.example",
            "sslmode": "verify-full",
            "sslrootcert": "/trusted/ca.pem",
            "hostaddr": "192.0.2.1",
        }
    finally:
        database.close()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "/tmp/db.sock"])
def test_local_addresses_do_not_query_external_dns(host):
    lookup = Mock()
    assert EncryptedResolver(lookup=lookup).resolve({"host": host}) is None
    lookup.assert_not_called()
