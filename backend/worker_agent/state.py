"""Owner-only local state, stable identity and a single-agent process lock."""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from worker_agent.security.auth import validate_worker_id
from worker_agent.security.private_files import (
    make_private,
    private_reader,
    reject_link,
)


class StateDirectory:
    def __init__(self, path: Path):
        self.path = path.expanduser().absolute()

    def prepare(self) -> None:
        reject_link(self.path)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        make_private(self.path, directory=True)

    def read_json(self, name: str) -> dict:
        with private_reader(self.path / name) as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise TypeError("Local worker state must be a JSON object")
        return value

    def write_json(self, name: str, value: dict) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=self.path)
        try:
            with os.fdopen(descriptor, "w") as stream:
                make_private(Path(temporary))
                json.dump(value, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path / name)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def lock(self, name: str = "agent.lock"):
        path = self.path / name
        reject_link(path)
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        acquired = False
        try:
            make_private(path)
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise RuntimeError(
                        "Another worker process already holds this state lock"
                    ) from error
            else:
                import fcntl

                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError(
                        "Another worker process already holds this state lock"
                    ) from error
            acquired = True
            yield
        finally:
            try:
                if acquired and os.name == "nt":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(descriptor)

    def identity(self, requested: str | None = None) -> str:
        self.prepare()
        if requested is not None:
            validate_worker_id(requested)
        with self.lock("identity.lock"):
            try:
                worker_id = self.read_json("identity.json")["worker_id"]
            except FileNotFoundError:
                worker_id = requested or str(uuid4())
                self.write_json("identity.json", {"worker_id": worker_id})
            validate_worker_id(worker_id)
            if requested is not None and requested != worker_id:
                raise ValueError(
                    "WORKER_ID does not match the persisted worker identity"
                )
            return worker_id
