"""Prepared CLI boundary regressions; no real controller/worker/deployment."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from lattice import cli


def arguments(**override):
    return SimpleNamespace(
        **{
            "github_url": "https://github.com/render-examples/flask-hello-world",
            "port": 8000,
            "start_command": '["gunicorn","app:app","--bind","0.0.0.0:8000"]',
            "pool_name": "development",
            "failover": False,
        }
        | override
    )


@pytest.mark.parametrize("start", ["[bad", '"gunicorn"', "[]", "[1]", '["a",""]'])
def test_bad_start_command_is_rejected_before_operator_connection(monkeypatch, start):
    connect = Mock()
    monkeypatch.setattr(cli, "admin_client", connect)
    with pytest.raises(cli.CLIError, match="start-command"):
        cli.deploy(arguments(start_command=start))
    connect.assert_not_called()


def test_markdown_repository_link_is_rejected_before_operator_connection(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(cli, "admin_client", connect)
    with pytest.raises(cli.CLIError, match="plain HTTPS repository URL"):
        cli.deploy(
            arguments(
                github_url="[https://github.com/example/app](https://github.com/example/app)"
            )
        )
    connect.assert_not_called()


def test_no_online_worker_causes_no_box_or_deployment_post(monkeypatch):
    client = Mock()
    connection = Mock()
    connection.__enter__ = Mock(return_value=client)
    connection.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(cli, "admin_client", Mock(return_value=connection))
    monkeypatch.setattr(cli, "find_pool", Mock(return_value={"pool_id": "pool"}))
    request = Mock(return_value={"workers": []})
    monkeypatch.setattr(cli, "request", request)
    with pytest.raises(cli.CLIError, match="No online pool workers"):
        cli.deploy(arguments())
    assert [call.args[1] for call in request.call_args_list] == ["GET"]


def test_safe_cli_error_is_printed_at_main_boundary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "deploy", Mock(side_effect=cli.CLIError("No online pool workers"))
    )
    assert (
        cli.main(
            [
                "deploy",
                "--env-file",
                "unused",
                "--pool-name",
                "development",
                "--github-url",
                "https://github.com/example/app",
            ]
        )
        == 2
    )
    assert "No online pool workers" in capsys.readouterr().err


def test_unexpected_value_error_contents_remain_private(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "deploy", Mock(side_effect=ValueError("private-test-token"))
    )
    assert (
        cli.main(
            [
                "deploy",
                "--env-file",
                "unused",
                "--pool-name",
                "development",
                "--github-url",
                "https://github.com/example/app",
            ]
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "ValueError" in output
    assert "private-test-token" not in output


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_continuous_monitor_recovers_from_temporary_http_failure(
    monkeypatch, capsys, status_code
):
    import httpx

    client = Mock()
    client.request.side_effect = [
        httpx.Response(status_code, text="upstream unavailable"),
        httpx.Response(200, json={"workers": [], "deployments": []}),
        KeyboardInterrupt(),
    ]
    connection = Mock(
        __enter__=Mock(return_value=client), __exit__=Mock(return_value=False)
    )
    monkeypatch.setattr(cli, "admin_client", Mock(return_value=connection))
    monkeypatch.setattr(
        cli, "find_pool", Mock(return_value={"pool_id": "p", "name": "trial"})
    )
    sleep = Mock()
    monkeypatch.setattr(cli.time, "sleep", sleep)
    args = SimpleNamespace(pool_name="trial", interval=2, once=False)
    with pytest.raises(KeyboardInterrupt):
        cli.monitor(args)
    output = capsys.readouterr().out
    assert "Current worker availability is unknown" in output
    assert "showing a fresh snapshot" in output
    assert "No laptops joined yet." in output
    assert client.request.call_count == 3
    assert sleep.call_args_list[0].args == (2,)
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


def test_monitor_backoff_is_capped_and_does_not_print_transport_secrets(
    monkeypatch, capsys
):
    import httpx

    client = Mock()
    client.request.side_effect = [httpx.ReadTimeout("private-test-credential")] * 7 + [
        KeyboardInterrupt()
    ]
    connection = Mock(
        __enter__=Mock(return_value=client), __exit__=Mock(return_value=False)
    )
    monkeypatch.setattr(cli, "admin_client", Mock(return_value=connection))
    monkeypatch.setattr(
        cli, "find_pool", Mock(return_value={"pool_id": "p", "name": "trial"})
    )
    sleep = Mock()
    monkeypatch.setattr(cli.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        cli.monitor(SimpleNamespace(pool_name="trial", interval=2, once=False))
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4, 8, 16, 30, 30, 30]
    assert "private-test-credential" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "status_code,once",
    [(401, False), (403, False), (404, False), (409, False), (502, True)],
)
def test_monitor_does_not_retry_rejected_requests_or_one_shot_checks(
    monkeypatch, status_code, once
):
    import httpx

    client = Mock()
    client.request.return_value = httpx.Response(
        status_code, json={"detail": "Request rejected"}
    )
    connection = Mock(
        __enter__=Mock(return_value=client), __exit__=Mock(return_value=False)
    )
    monkeypatch.setattr(cli, "admin_client", Mock(return_value=connection))
    monkeypatch.setattr(
        cli, "find_pool", Mock(return_value={"pool_id": "p", "name": "trial"})
    )
    sleep = Mock()
    monkeypatch.setattr(cli.time, "sleep", sleep)
    with pytest.raises(cli.ControllerRequestError):
        cli.monitor(SimpleNamespace(pool_name="trial", interval=2, once=once))
    sleep.assert_not_called()
    assert client.request.call_count == 1


def test_monitor_retries_initial_pool_lookup_before_starting_snapshot_poll(monkeypatch):
    client = Mock()
    connection = Mock(
        __enter__=Mock(return_value=client), __exit__=Mock(return_value=False)
    )
    monkeypatch.setattr(cli, "admin_client", Mock(return_value=connection))
    lookup = Mock(
        side_effect=[cli.ControllerRequestError(502), {"pool_id": "p", "name": "trial"}]
    )
    monkeypatch.setattr(cli, "find_pool", lookup)
    request = Mock(side_effect=KeyboardInterrupt())
    monkeypatch.setattr(cli, "request", request)
    monkeypatch.setattr(cli.time, "sleep", Mock())
    with pytest.raises(KeyboardInterrupt):
        cli.monitor(SimpleNamespace(pool_name="trial", interval=2, once=False))
    assert lookup.call_count == 2
    assert request.call_count == 1


def test_pool_switch_reports_actionable_error_before_docker_or_enrollment(
    tmp_path, capsys
):
    from worker_agent.state import StateDirectory

    state = StateDirectory(tmp_path)
    state.prepare()
    state.write_json(
        "connection.json",
        {
            "server": "https://api.example.com",
            "pool_name": "old-pool",
            "enrolled": True,
        },
    )
    before = state.read_json("connection.json")
    assert (
        cli.main(
            [
                "connect",
                "--server",
                "https://api.example.com",
                "--pool-name",
                "cloud",
                "--state-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "another server/pool" in output and "--state-dir" in output
    assert "ValueError" not in output
    assert state.read_json("connection.json") == before


@pytest.mark.parametrize("failure", [FileNotFoundError, ConnectionRefusedError])
def test_missing_local_control_explains_matching_state_directory(
    tmp_path, monkeypatch, capsys, failure
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "worker_agent.communication.control.send_control",
        AsyncMock(side_effect=failure("private-test-input")),
    )
    assert cli.main(["status", "--state-dir", str(tmp_path)]) == 2
    output = capsys.readouterr().err
    assert "No running worker control endpoint" in output
    assert "same --state-dir" in output
    assert "private-test-input" not in output


def test_cli_exposes_installed_package_version(monkeypatch, capsys):
    monkeypatch.setattr("importlib.metadata.version", lambda package: "0.3.2")
    with pytest.raises(SystemExit) as result:
        cli.main(["--version"])
    assert result.value.code == 0
    assert "lattice 0.3.2" in capsys.readouterr().out


def test_doctor_reports_saved_pool_and_never_dumps_private_values(
    tmp_path, monkeypatch, capsys
):
    import json
    from pathlib import Path

    from lattice import diagnostics
    from worker_agent.state import StateDirectory

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    state = StateDirectory(tmp_path / ".lattice/worker")
    state.prepare()
    state.write_json(
        "connection.json",
        {
            "server": "https://api.example.com",
            "pool_name": "old-pool",
            "enrolled": True,
            "token": "private-test-worker-token",
        },
    )
    state.write_json("worker.json", {"worker_token": "private-test-worker-token"})
    client = Mock()
    client.info.return_value = {
        "OSType": "linux",
        "Architecture": "x86_64",
        "NCPU": 4,
        "MemTotal": 1024,
        "secret": "private-test-docker-token",
    }
    client.containers.list.return_value = []
    monkeypatch.setattr(diagnostics, "open_local_docker", lambda settings: client)
    connection = Mock()
    connection.get.return_value = __import__("httpx").Response(
        200, json={"status": "healthy"}
    )
    monkeypatch.setattr(
        diagnostics.httpx,
        "Client",
        lambda **kwargs: Mock(
            __enter__=Mock(return_value=connection), __exit__=Mock(return_value=False)
        ),
    )
    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "private-test" not in output
    report = json.loads(output)
    assert report["profiles"][0]["pool"] == "old-pool"
    assert report["profiles"][0]["control_endpoint_present"] is False
    assert report["docker"]["linux_engine"] is True
    assert report["controller"]["healthy"] is True
    client.close.assert_called_once()


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("unauthorized private-test-token", "GHCR rejected"),
        ("error storing credentials: keychain private-test-token", "could not save"),
        ("lookup ghcr.io: no such host private-test-token", "cannot resolve"),
        ("unexpected private-test-token", "Docker registry login failed"),
    ],
)
def test_registry_login_reports_safe_category_and_keeps_token_off_command_line(
    tmp_path, monkeypatch, capsys, detail, expected
):
    token_file = tmp_path / "token.txt"
    token_file.write_text("private-test-token\n")
    token_file.chmod(0o600)
    run = Mock(
        return_value=__import__("subprocess").CompletedProcess(
            [], 1, stdout="", stderr=detail
        )
    )
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert (
        cli.main(
            ["registry-login", "--username", "fixture", "--token-file", str(token_file)]
        )
        == 2
    )
    output = capsys.readouterr().err
    assert expected in output
    assert "private-test-token" not in output
    assert "private-test-token" not in " ".join(run.call_args.args[0])
    assert run.call_args.kwargs["input"] == "private-test-token"
