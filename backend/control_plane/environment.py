"""Explicit private configuration loading without exporting unrelated secrets."""

from pathlib import Path

from worker_agent.security.private_files import private_reader

from control_plane.config import Settings


def load_settings_file(path: Path):
    if path.is_symlink():
        raise OSError("Private configuration cannot be a symlink")
    # Validate the actual opened descriptor's owner and access policy.
    with private_reader(path):
        pass
    return Settings(_env_file=path, _env_file_encoding="utf-8-sig")
