"""
Shared pytest fixtures.

- `client`: a TestClient wired to a fresh in-memory fake Firestore per
  test (tests/fake_firestore.py — mirrors firestore_db.FirestoreDB's
  exact interface), with the Hugging Face LLM client, the business
  database, and Paymob's network calls all mocked out. No real Firestore
  project, network access, or credentials needed for this suite — real
  Firestore connectivity is verified separately via
  scripts/smoke_test.py against real credentials.
"""
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("APP_MODE", "local")
os.environ.setdefault("HF_TOKEN", "test-token")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DEV_ACCESS_PASSWORD", "letmein")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("PAYMOB_API_KEY", "test_key")
os.environ.setdefault("PAYMOB_INTEGRATION_ID", "123")
os.environ.setdefault("PAYMOB_IFRAME_ID", "456")
os.environ.setdefault("PAYMOB_HMAC_SECRET", "test_hmac_secret")


class _FakeChoice:
    def __init__(self, content):
        self.message = types.SimpleNamespace(content=content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeInferenceClient:
    """Stands in for huggingface_hub.InferenceClient — no network calls."""
    def __init__(self, *a, **kw):
        pass

    def chat_completion(self, messages, max_tokens=None, temperature=None):
        prompt = messages[0]["content"]
        if '"target_metric"' in prompt and "NOW ANALYZE THIS" in prompt:
            return _FakeResponse(
                '{"target_metric":"revenue","date_column":"order_date",'
                '"dimensions":["region"],"tables":["sales"],'
                '"possible_causes":["customer_loss"],"comparison_period":null,'
                '"analysis_type":"trend","requires_benchmark":false}'
            )
        if "NOW GENERATE THE SQL" in prompt:
            return _FakeResponse("SELECT * FROM sales;")
        return _FakeResponse("Mocked interpretation sentence.")


@pytest.fixture()
def sample_df():
    return pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=100, freq="D"),
        "revenue": np.random.default_rng(0).normal(1000, 300, 100).round(2),
        "region": np.random.default_rng(1).choice(["North", "South"], 100),
    })


@pytest.fixture()
def client(monkeypatch, sample_df):
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "InferenceClient", _FakeInferenceClient)

    class _FakeDataSource:
        dialect_note = None

        def get_schema(self):
            return {"sales": [{"column": "order_date", "type": "date", "nullable": "YES"}]}

        def get_latest_date(self, table, col):
            return pd.Timestamp("2024-12-31")

        def execute_sql(self, query):
            return sample_df

    import main
    monkeypatch.setattr(main, "get_datasource_for_dataset", lambda user_id, dataset_id, db: _FakeDataSource())

    import paymob
    monkeypatch.setattr(paymob, "_authenticate", lambda: "fake_auth_token")
    _order_counter = {"n": 999888}

    def _fake_create_order(auth_token, amount_cents, merchant_order_id=None):
        _order_counter["n"] += 1
        return _order_counter["n"]

    monkeypatch.setattr(paymob, "_create_order", _fake_create_order)
    monkeypatch.setattr(paymob, "_request_payment_key", lambda auth_token, order_id, amount_cents, billing_data: "fake_payment_key")

    from tests.fake_firestore import FakeFirestoreDB
    fake_db = FakeFirestoreDB()

    import main
    app = main.app
    app.dependency_overrides[main.get_db] = lambda: fake_db
    app.state.fake_db = fake_db

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def signed_up_user(client):
    """Returns (auth_headers, email) for a freshly signed-up user."""
    email = "test@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret123", "full_name": "Test User"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.fixture()
def signed_up_user_factory(client):
    """Callable(email) -> (auth_headers, email) for tests that need more
    than one distinct account (e.g. team invites)."""
    def _make(email: str):
        r = client.post("/auth/signup", json={"email": email, "password": "supersecret123", "full_name": "Teammate"})
        assert r.status_code == 200
        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, email
    return _make


def _activate_subscription(client, auth: dict, email: str, plan: str) -> dict:
    """Runs a real checkout + correctly-signed webhook for `email` on `plan`,
    same flow the `subscribed_user` fixture below uses for the default case."""
    import hashlib
    import hmac

    import paymob

    r = client.post("/billing/checkout", json={"plan": plan}, headers=auth)
    assert r.status_code == 200
    checkout = r.json()

    fake_db = client.app.state.fake_db
    txn_id = checkout["transaction_id"]
    user = fake_db.get_user_by_email(email)
    txn = fake_db.get_transaction(user.id, txn_id)
    order_id = txn.paymob_order_id

    webhook_obj = {
        "id": 1, "amount_cents": checkout["amount_cents"], "created_at": "2024-01-01T00:00:00",
        "currency": checkout["currency"], "error_occured": False, "has_parent_transaction": False,
        "integration_id": 123, "is_3d_secure": True, "is_auth": False, "is_capture": False,
        "is_refunded": False, "is_standalone_payment": True, "is_voided": False,
        "order": {"id": int(order_id)}, "owner": 1, "pending": False,
        "source_data": {"pan": "1234", "sub_type": "Visa", "type": "card"}, "success": True,
    }
    hmac_str = paymob.build_transaction_hmac_string(webhook_obj)
    computed_hmac = hmac.new(b"test_hmac_secret", hmac_str.encode(), hashlib.sha512).hexdigest()

    r = client.post(f"/payments/paymob/webhook?hmac={computed_hmac}", json={"obj": webhook_obj})
    assert r.status_code == 200
    return checkout


@pytest.fixture()
def subscribed_user(client, signed_up_user):
    """Returns auth_headers for a user with an active Pro subscription (gives
    generous daily headroom — 20/day — for tests that fire several /analyze
    calls in a row; Starter/Growth are exercised directly in test_billing.py)."""
    auth, email = signed_up_user
    _activate_subscription(client, auth, email, "pro")

    return auth
