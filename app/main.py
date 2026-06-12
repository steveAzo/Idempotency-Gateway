import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes.payments import router as payments_router
from app.store import cleanup_expired_keys


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_expired_keys())
    yield
    task.cancel()


app = FastAPI(title="Idempotency Gateway", lifespan=lifespan)

app.include_router(payments_router)


@app.get("/")
def read_root():
    return {"message": "Idempotency Gateway is running"}
