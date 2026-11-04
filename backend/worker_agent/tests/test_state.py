import json

import pytest
from worker_agent.state import StateDirectory


def test_identity_persists_and_files_are_private(tmp_path):
    state = StateDirectory(tmp_path / "state")
    worker_id = state.identity()
    assert StateDirectory(state.path).identity() == worker_id
    assert state.path.stat().st_mode & 0o777 == 0o700
    assert (state.path / "identity.json").stat().st_mode & 0o777 == 0o600


def test_provisioned_identity_cannot_silently_change(tmp_path):
    state = StateDirectory(tmp_path)
    assert state.identity("W-001") == "W-001"
    with pytest.raises(ValueError, match="does not match"):
        state.identity("W-002")


def test_process_lock_prevents_duplicate_worker(tmp_path):
    state = StateDirectory(tmp_path)
    state.prepare()
    with (
        state.lock(),
        pytest.raises(RuntimeError, match="Another worker"),
        state.lock(),
    ):
        pass


def test_symlink_state_and_public_identity_are_rejected(tmp_path):
    state = StateDirectory(tmp_path / "state")
    state.prepare()
    (state.path / "identity.json").write_text(json.dumps({"worker_id": "W-001"}))
    (state.path / "identity.json").chmod(0o644)
    with pytest.raises(PermissionError):
        state.identity()
    link = tmp_path / "link"
    link.symlink_to(state.path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        StateDirectory(link).prepare()
