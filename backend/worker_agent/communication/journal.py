"""Private local request ledger, not a Control Plane database schema."""

import sqlite3
import threading

from shared.contracts import CommandResult

from worker_agent.security.policy import fingerprint
from worker_agent.security.private_files import make_private, reject_link


class RequestJournal:
    def __init__(self, state):
        path = state.path / "requests.sqlite3"
        reject_link(path)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        make_private(path)
        self.lock = threading.RLock()
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, "
            "payload_hash TEXT NOT NULL, result_json TEXT)"
        )
        self.connection.commit()

    def begin(self, command) -> CommandResult | None:
        request_id = str(command.request_id)
        digest = fingerprint(command)
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT payload_hash, result_json FROM requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError("Request ID was reused with different parameters")
                return CommandResult.model_validate_json(row[1]) if row[1] else None
            self.connection.execute(
                "INSERT INTO requests (request_id, payload_hash) VALUES (?, ?)",
                (request_id, digest),
            )
        return None

    def finish(self, result: CommandResult) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE requests SET result_json = ? WHERE request_id = ?",
                (result.model_dump_json(), str(result.request_id)),
            )

    def close(self) -> None:
        self.connection.close()
