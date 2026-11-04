from unittest.mock import Mock

from worker_agent.communication.dispatcher import CommandDispatcher
from worker_agent.communication.journal import RequestJournal
from worker_agent.state import StateDirectory
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command


def test_restart_replays_result_without_reexecuting_or_storing_environment(tmp_path):
    state = StateDirectory(tmp_path)
    state.prepare()
    runtime = Mock()
    runtime.run.return_value = "container-1"
    runtime.inspect.return_value.event.return_value = Mock()
    command = run_command(environment_variables={"SECRET": "sensitive-value"})
    journal = RequestJournal(state)
    first = CommandDispatcher(runtime, journal, settings(tmp_path)).execute(command)
    assert first.result.success
    journal.close()
    journal = RequestJournal(state)
    dispatcher = CommandDispatcher(runtime, journal, settings(tmp_path))
    assert dispatcher.execute(command).result == first.result
    runtime.run.assert_called_once()
    changed = command.model_copy(update={"ram_limit_mb": 512})
    assert not dispatcher.execute(changed).result.success
    journal.close()
    assert b"sensitive-value" not in (tmp_path / "requests.sqlite3").read_bytes()


def test_pending_request_is_recoverable_after_crash(tmp_path):
    state = StateDirectory(tmp_path)
    state.prepare()
    journal = RequestJournal(state)
    command = run_command()
    assert journal.begin(command) is None
    journal.close()
    journal = RequestJournal(state)
    assert journal.begin(command) is None
    journal.close()


def test_failure_redacts_worker_token(tmp_path):
    state = StateDirectory(tmp_path)
    state.prepare()
    runtime = Mock()
    runtime.run.side_effect = ValueError("test-token must be hidden")
    journal = RequestJournal(state)
    result = (
        CommandDispatcher(runtime, journal, settings(tmp_path))
        .execute(run_command())
        .result
    )
    assert result.success is False
    assert "test-token" not in result.message
    journal.close()
