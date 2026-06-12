import asyncio
import time

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.config import KEY_TTL_SECONDS
from app.models import PaymentRequest, StoredResponse
from app.store import hash_body, idempotency_store, in_flight_locks

router = APIRouter()


@router.post("/process-payment", status_code=201)
async def process_payment(
    payment: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    incoming_hash = hash_body(payment.model_dump())

    if idempotency_key not in in_flight_locks:
        in_flight_locks[idempotency_key] = asyncio.Lock()

    async with in_flight_locks[idempotency_key]:
        if idempotency_key in idempotency_store:
            stored = idempotency_store[idempotency_key]

            if time.time() - stored.created_at > KEY_TTL_SECONDS:
                # Expired — evict and fall through to fresh processing
                del idempotency_store[idempotency_key]
            else:
                if stored.request_hash != incoming_hash:
                    raise HTTPException(
                        status_code=422,
                        detail="Idempotency key already used for a different request body.",
                    )
                response = JSONResponse(
                    content=stored.body, status_code=stored.status_code
                )
                response.headers["X-Cache-Hit"] = "true"
                return response

        # Simulate payment processing
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
