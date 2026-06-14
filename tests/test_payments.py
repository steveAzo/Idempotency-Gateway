import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import idempotency_store, in_flight_locks

KEY = "test-idempotency-key-abc-123"
PAYMENT = {"amount": 100, "currency": "GHS"}


@pytest.fixture(autouse=True)
def clear_store():
    """Reset shared in-memory state before and after every test."""
    idempotency_store.clear()
    in_flight_locks.clear()
    yield
    idempotency_store.clear()
    in_flight_locks.clear()


@pytest.fixture(autouse=True)
def skip_processing_delay(monkeypatch):
    """Zero out the simulated payment delay so tests run instantly."""
    monkeypatch.setattr("app.routes.payments.PROCESSING_DELAY_SECONDS", 0)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def post_payment(client, key=KEY, body=None):
    return client.post(
        "/process-payment",
        json=body if body is not None else PAYMENT,
        headers={"Idempotency-Key": key},
    )


class TestFirstRequest:
    def test_returns_201(self, client):
        assert post_payment(client).status_code == 201

    def test_response_body_contains_charge_message(self, client):
        data = post_payment(client).json()
        assert data["status"] == "success"
        assert "Charged 100.0 GHS" in data["message"]

    def test_no_cache_hit_header_on_first_request(self, client):
        assert "x-cache-hit" not in post_payment(client).headers


class TestDuplicateRequest:
    def test_duplicate_returns_201(self, client):
        post_payment(client)
        assert post_payment(client).status_code == 201

    def test_duplicate_returns_identical_body(self, client):
        first = post_payment(client).json()
        second = post_payment(client).json()
        assert first == second

    def test_duplicate_sets_cache_hit_header(self, client):
        post_payment(client)
        response = post_payment(client)
        assert response.headers.get("x-cache-hit") == "true"

    def test_unique_keys_are_independent(self, client):
        post_payment(client, key="key-one")
        post_payment(client, key="key-two")
        assert post_payment(client, key="key-one").headers.get("x-cache-hit") == "true"
        assert post_payment(client, key="key-two").headers.get("x-cache-hit") == "true"


class TestConflict:
    def test_different_body_returns_422(self, client):
        post_payment(client)
        assert post_payment(client, body={"amount": 500, "currency": "GHS"}).status_code == 422

    def test_different_body_error_message(self, client):
        post_payment(client)
        response = post_payment(client, body={"amount": 500, "currency": "GHS"})
        assert response.json()["detail"] == (
            "Idempotency key already used for a different request body."
        )

    def test_different_currency_also_conflicts(self, client):
        post_payment(client)
        assert post_payment(client, body={"amount": 100, "currency": "USD"}).status_code == 422


class TestValidation:
    def test_missing_idempotency_key_returns_422(self, client):
        assert client.post("/process-payment", json=PAYMENT).status_code == 422

    def test_missing_body_returns_422(self, client):
        assert client.post(
            "/process-payment", headers={"Idempotency-Key": KEY}
        ).status_code == 422

    def test_missing_amount_field_returns_422(self, client):
        assert client.post(
            "/process-payment",
            json={"currency": "GHS"},
            headers={"Idempotency-Key": KEY},
        ).status_code == 422
