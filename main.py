import asyncio
import hashlib
import json
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Idempotency Gateway")


# models
class PaymentRequest(BaseModel):
    amount: float
    currency: str


class StoredResponse(BaseModel):
    status_code: int
    body: dict
    request_hash: str
    created_at: float 


# in-memory store
idempotency_store: dict[str, StoredResponse] = {}

KEY_TTL_SECONDS = 86400  

# one asyncio.Lock per idempotency key — keeps concurrent identical requests serialised
in_flight_locks: dict[str, asyncio.Lock] = {}


def hash_body(body: dict) -> str:
    """Return a stable SHA-256 fingerprint of a dict (order-independent)."""
    serialized = json.dumps(body, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


@app.get("/")
def read_root():
    return {"message": "Idempotency Gateway is running"}


@app.post("/process-payment", status_code=201)
async def process_payment(
    payment: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    incoming_hash = hash_body(payment.model_dump())

    # Create a lock for this key if one doesn't exist yet
    if idempotency_key not in in_flight_locks:
        in_flight_locks[idempotency_key] = asyncio.Lock()

    async with in_flight_locks[idempotency_key]:
        # --- Idempotency check (must live INSIDE the lock) ---
        if idempotency_key in idempotency_store:
            stored = idempotency_store[idempotency_key]

            if time.time() - stored.created_at > KEY_TTL_SECONDS:
                # Key has expired — evict it and fall through to fresh processing
                del idempotency_store[idempotency_key]
            else:
                if stored.request_hash != incoming_hash:
                    raise HTTPException(
                        status_code=422,
                        detail="Idempotency key already used for a different request body.",
                    )

                response = JSONResponse(content=stored.body, status_code=stored.status_code)
                response.headers["X-Cache-Hit"] = "true"
                return response

        # Simulate payment processing (2-second delay)
        await asyncio.sleep(2)
        result = {
            "status": "success",
            "message": f"Charged {payment.amount} {payment.currency}",
        }

        idempotency_store[idempotency_key] = StoredResponse(
            status_code=201,
            body=result,
            request_hash=incoming_hash,
            created_at=time.time(),
        )

        return result



