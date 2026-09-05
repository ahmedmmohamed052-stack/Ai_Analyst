import hashlib
import hmac


def test_plans_endpoint_lists_all_three_plans(client):
    r = client.get("/plans")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"starter", "growth", "pro"}
    assert body["starter"]["price_usd"] == 24.0
    assert body["growth"]["price_usd"] == 69.0
    assert body["pro"]["price_usd"] == 179.0
    assert body["pro"]["max_seats"] > 1
    assert body["starter"]["max_seats"] == 1


def test_checkout_requires_auth(client):
    r = client.post("/billing/checkout", json={"plan": "starter"})
    assert r.status_code == 401


def test_checkout_rejects_invalid_plan(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/checkout", json={"plan": "not-a-real-plan"}, headers=auth)
    assert r.status_code == 400


def test_checkout_creates_pending_transaction_and_iframe_url(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/checkout", json={"plan": "starter"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "starter"
    assert body["iframe_url"].startswith("https://accept.paymob.com/")
    assert body["amount_cents"] > 0


def test_analyze_blocked_without_subscription(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/analyze", json={"question": "why did revenue drop?", "dataset_id": "ds1"}, headers=auth)
    assert r.status_code == 402


def test_webhook_bad_hmac_rejected(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/checkout", json={"plan": "starter"}, headers=auth)
    checkout = r.json()

    webhook_obj = {
        "id": 1, "amount_cents": checkout["amount_cents"], "created_at": "2024-01-01T00:00:00",
        "currency": checkout["currency"], "success": True,
        "order": {"id": 999}, "source_data": {},
    }
    r = client.post("/payments/paymob/webhook?hmac=not-a-real-signature", json={"obj": webhook_obj})
    assert r.status_code == 400


def test_webhook_valid_hmac_activates_subscription(client, subscribed_user):
    # `subscribed_user` fixture already ran checkout + a correctly-signed
    # webhook — if it activated properly, /me should show an active plan.
    r = client.get("/me", headers=subscribed_user)
    body = r.json()
    assert body["subscription"] is not None
    assert body["subscription"]["plan"] == "pro"


def test_analyze_allowed_after_subscription_activated(client, subscribed_user):
    r = client.post("/analyze", json={"question": "why did revenue drop?", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 200
    assert "report_id" in r.json()


def _order_id_for(client, email, transaction_id):
    fake_db = client.app.state.fake_db
    user = fake_db.get_user_by_email(email)
    txn = fake_db.get_transaction(user.id, transaction_id)
    return txn.paymob_order_id


def test_renewal_extends_from_existing_expiry_not_from_now(client, subscribed_user):
    """A second successful payment while a subscription is still active should
    extend the expiry forward, not reset it to now + duration."""
    import hashlib
    import hmac

    import paymob

    r_before = client.get("/me", headers=subscribed_user)
    expiry_before = r_before.json()["subscription"]["expires_at"]

    r = client.post("/billing/checkout", json={"plan": "starter"}, headers=subscribed_user)
    checkout = r.json()
    order_id = _order_id_for(client, "test@example.com", checkout["transaction_id"])

    webhook_obj = {
        "id": 2, "amount_cents": checkout["amount_cents"], "created_at": "2024-01-01T00:00:00",
        "currency": checkout["currency"], "error_occured": False, "has_parent_transaction": False,
        "integration_id": 123, "is_3d_secure": True, "is_auth": False, "is_capture": False,
        "is_refunded": False, "is_standalone_payment": True, "is_voided": False,
        "order": {"id": int(order_id)}, "owner": 1, "pending": False,
        "source_data": {"pan": "1234", "sub_type": "Visa", "type": "card"}, "success": True,
    }
    hmac_str = paymob.build_transaction_hmac_string(webhook_obj)
    computed_hmac = hmac.new(b"test_hmac_secret", hmac_str.encode(), hashlib.sha512).hexdigest()
    client.post(f"/payments/paymob/webhook?hmac={computed_hmac}", json={"obj": webhook_obj})

    r_after = client.get("/me", headers=subscribed_user)
    expiry_after = r_after.json()["subscription"]["expires_at"]

    assert expiry_after > expiry_before


def test_failed_payment_does_not_activate_subscription(client, signed_up_user):
    import hashlib
    import hmac

    import paymob

    auth, email = signed_up_user
    r = client.post("/billing/checkout", json={"plan": "starter"}, headers=auth)
    checkout = r.json()
    order_id = _order_id_for(client, email, checkout["transaction_id"])

    webhook_obj = {
        "id": 3, "amount_cents": checkout["amount_cents"], "created_at": "2024-01-01T00:00:00",
        "currency": checkout["currency"], "error_occured": False, "has_parent_transaction": False,
        "integration_id": 123, "is_3d_secure": True, "is_auth": False, "is_capture": False,
        "is_refunded": False, "is_standalone_payment": True, "is_voided": False,
        "order": {"id": int(order_id)}, "owner": 1, "pending": False,
        "source_data": {"pan": "1234", "sub_type": "Visa", "type": "card"}, "success": False,
    }
    hmac_str = paymob.build_transaction_hmac_string(webhook_obj)
    computed_hmac = hmac.new(b"test_hmac_secret", hmac_str.encode(), hashlib.sha512).hexdigest()
    client.post(f"/payments/paymob/webhook?hmac={computed_hmac}", json={"obj": webhook_obj})

    r = client.get("/me", headers=auth)
    assert r.json()["subscription"] is None

    r = client.post("/analyze", json={"question": "test", "dataset_id": "ds1"}, headers=auth)
    assert r.status_code == 402
