from pydantic import BaseModel


class PaymentRequest(BaseModel):
    amount: float
    currency: str


class StoredResponse(BaseModel):
    status_code: int
    body: dict
    request_hash: str
    created_at: float  
