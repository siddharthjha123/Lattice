"""Configuration and public API boundary regressions."""

import os
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.environment import load_settings_file
from control_plane.main import create_app


def test_private_configuration_parses_lists_without_exporting_tunnel_secret(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("CLOUDFLARE_TUNNEL_TOKEN", raising=False)
    path = tmp_path / "server.env"
    path.write_text(
        'DATABASE_URL=sqlite://\nADMIN_TOKEN=private-admin-value\nCLOUDFLARE_TUNNEL_TOKEN=unrelated-secret\nCORS_ORIGINS=["https://example.com"]\nEXPOSE_API_DOCS=false\n'
    )
    path.chmod(0o600)
    config = load_settings_file(path)
    assert config.DATABASE_URL == "sqlite://"
    assert config.CORS_ORIGINS == ["https://example.com"]
    assert config.EXPOSE_API_DOCS is False
    assert "private-admin-value" not in repr(config)
    assert "CLOUDFLARE_TUNNEL_TOKEN" not in os.environ
    assert not hasattr(config, "CLOUDFLARE_TUNNEL_TOKEN")


def test_private_configuration_rejects_public_files_and_symlinks(tmp_path):
    path = tmp_path / "server.env"
    path.write_text("ADMIN_TOKEN=private\n")
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        load_settings_file(path)
    path.chmod(0o600)
    link = tmp_path / "link.env"
    link.symlink_to(path)
    with pytest.raises(OSError):
        load_settings_file(link)


@pytest.mark.parametrize(
    "prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"]
)
def test_ca_file_forces_verified_tls_for_all_supported_url_formats(tmp_path, prefix):
    ca = tmp_path / "ca.pem"
    ca.write_text("test certificate path")
    config = Settings(
        DATABASE_URL=prefix
        + "user:test-password@database.example/test?sslmode=require",
        DATABASE_CA_FILE=ca,
    )
    query = parse_qs(urlsplit(config.normalized_database_url).query)
    assert query["sslmode"] == ["verify-full"]
    assert query["sslrootcert"] == [str(ca)]


def test_untrusted_host_is_rejected(client):
    response = client.get("/health", headers={"Host": "attacker.example"})
    assert response.status_code == 400


def test_public_mode_hides_docs_and_has_exact_cors_allowlist(context):
    context.config.EXPOSE_API_DOCS = False
    context.config.CORS_ORIGINS = ["https://example.com"]
    with TestClient(create_app(context.config, context)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/api/workers").status_code == 401
        headers = {
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        response = client.options("/api/boxes", headers=headers)
        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "https://example.com"
        )
        assert (
            client.options(
                "/api/boxes", headers=headers | {"Origin": "https://attacker.example"}
            ).status_code
            == 400
        )


def test_direct_dns_preserves_tls_hostname_and_does_not_pin_addresses(monkeypatch):
    from types import SimpleNamespace

    from control_plane.database.resolution import resolve_connection_address

    values = iter(["192.0.2.10", "192.0.2.11"])

    def resolve(*args, **kwargs):
        assert args == ("database.example", "A")
        assert kwargs["lifetime"] == 3 and not kwargs["search"]
        return [SimpleNamespace(address=next(values))]

    monkeypatch.setattr("dns.resolver.resolve", resolve)
    parameters = {
        "host": "database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
    }
    assert resolve_connection_address(parameters) == "192.0.2.10"
    assert resolve_connection_address(parameters) == "192.0.2.11"
    assert parameters == {
        "host": "database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
    }


def test_direct_dns_refuses_ambiguous_multi_host_url_and_skips_literal_ip():
    from control_plane.database.resolution import resolve_connection_address

    with pytest.raises(ValueError, match="one database hostname"):
        resolve_connection_address({"host": "one.example,two.example"})
    assert resolve_connection_address({"host": "127.0.0.1"}) is None


@pytest.mark.parametrize("failure", ["timeout", "nameservers", "network"])
def test_transient_direct_dns_uses_native_resolution_without_logging_host(
    monkeypatch, caplog, failure
):
    import dns.exception
    import dns.resolver

    from control_plane.database.resolution import resolve_connection_address

    errors = {
        "timeout": dns.exception.Timeout,
        "nameservers": dns.resolver.NoNameservers,
        "network": OSError,
    }

    def unavailable(*args, **kwargs):
        raise errors[failure]()

    monkeypatch.setattr("dns.resolver.resolve", unavailable)
    parameters = {
        "host": "private-database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
    }
    original = parameters.copy()
    assert resolve_connection_address(parameters) is None
    assert parameters == original
    assert "using native hostname resolution" in caplog.text
    assert "private-database.example" not in caplog.text


def test_direct_dns_failure_clears_previous_address_and_refreshes_next_connection(
    monkeypatch,
):
    from types import SimpleNamespace

    import dns.exception

    from control_plane.database.session import Database

    answers = iter(["192.0.2.10", None, "192.0.2.11"])

    def resolve(*args, **kwargs):
        address = next(answers)
        if address is None:
            raise dns.exception.Timeout()
        return [SimpleNamespace(address=address)]

    monkeypatch.setattr("dns.resolver.resolve", resolve)
    database = Database(
        "postgresql+psycopg://user@database.example/test", resolve_host=True
    )
    parameters = {
        "host": "database.example",
        "sslmode": "verify-full",
        "sslrootcert": "/trusted/ca.pem",
    }
    try:
        callbacks = list(database.engine.dialect.dispatch.do_connect)
        for expected in ["192.0.2.10", None, "192.0.2.11"]:
            for callback in callbacks:
                callback(database.engine.dialect, None, [], parameters)
            assert parameters.get("hostaddr") == expected
            assert parameters["host"] == "database.example"
            assert parameters["sslmode"] == "verify-full"
            assert parameters["sslrootcert"] == "/trusted/ca.pem"
    finally:
        database.close()


def test_two_workers_can_join_one_pool_concurrently(client):
    from concurrent.futures import ThreadPoolExecutor

    from .conftest import PAYLOAD

    pool = client.post("/api/pools", json={"name": "concurrent-trial"}).json()

    def join(index):
        return client.post(
            "/api/pools/join",
            json={
                "pool_name": pool["name"],
                "pool_code": pool["pool_code"],
                "worker_token": "lattice_wk_" + str(index) * 43,
                "worker": PAYLOAD | {"worker_id": f"concurrent-{index}"},
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(join, [1, 2]))
    assert [response.status_code for response in responses] == [200, 200]
    status = client.get(f"/api/pools/{pool['pool_id']}/status").json()
    assert len(status["workers"]) == 2 and status["joins_used"] == 2
