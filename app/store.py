import asyncio
import hashlib
import json
import time

from app.config import CLEANUP_INTERVAL_SECONDS, KEY_TTL_SECONDS
from app.models import StoredResponse

idempotency_store: dict[str, StoredResponse] = {}
in_flight_locks: dict[str, asyncio.Lock] = {}


def hash_body(body: dict) -> str:
    """Stable SHA-256 fingerprint of a dict — order-independent."""
    serialized = json.dumps(body, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def cleanup_expired_keys() -> None:
    """Background task: sweeps the store every hour, evicting keys older than TTL."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        expired = [
            key
            for key, stored in list(idempotency_store.items())
            if now - stored.created_at > KEY_TTL_SECONDS
        ]
        for key in expired:
            del idempotency_store[key]
            in_flight_locks.pop(key, None)
