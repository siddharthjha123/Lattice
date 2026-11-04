"""Expiring pool enrollment; join codes never authorize management operations."""

import secrets
import time
from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from control_plane.database.models import Pool
from control_plane.services.auth import hash_token
from control_plane.services.contracts import aware


def new_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "LTC-" + "-".join(
        "".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4)
    )


def code_hash(name, code, config):
    return hash_token("pool:" + name + ":" + code, config)


def pool_record(pool):
    return {
        "pool_id": str(pool.pool_id),
        "name": pool.name,
        "join_code_expires_at": aware(pool.code_expires_at).isoformat(),
        "joins_used": pool.joins_used,
        "max_joins": pool.max_joins,
        "created_at": aware(pool.created_at).isoformat(),
    }


def create_pool(session, name, config, *, hours=24, max_joins=10):
    existing = session.query(Pool).filter_by(name=name).first()
    if existing is not None and existing.deleted_at is not None:
        raise HTTPException(
            409, "Pool name belongs to deleted history; choose a new pool name"
        )
    if existing is not None:
        raise HTTPException(
            409, "Pool name already exists; rotate its join code explicitly"
        )
    code = new_code()
    pool = Pool(
        pool_id=uuid4(),
        name=name,
        code_hash=code_hash(name, code, config),
        code_expires_at=datetime.now(UTC) + timedelta(hours=hours),
        max_joins=max_joins,
        joins_used=0,
    )
    session.add(pool)
    session.flush()
    return pool_record(pool) | {"pool_code": code}


class JoinLimiter:
    """Bounded process-local throttling for the single-controller deployment."""

    def __init__(self):
        self.clients = OrderedDict()
        self.global_attempts = deque(maxlen=1000)

    def check(self, key):
        now = time.monotonic()
        while self.global_attempts and now - self.global_attempts[0] > 60:
            self.global_attempts.popleft()
        if len(self.global_attempts) >= 1000:
            raise HTTPException(
                429, "Enrollment temporarily busy", headers={"Retry-After": "60"}
            )
        self.global_attempts.append(now)
        attempts = self.clients.pop(key, deque(maxlen=20))
        while attempts and now - attempts[0] > 60:
            attempts.popleft()
        self.clients[key] = attempts
        if len(self.clients) > 4096:
            self.clients.popitem(last=False)
        if len(attempts) >= 20:
            raise HTTPException(
                429,
                "Too many join attempts; wait one minute",
                headers={"Retry-After": "60"},
            )
        attempts.append(now)
