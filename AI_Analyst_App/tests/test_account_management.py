import re


def _extract_token_from_log(caplog, marker):
    """Password reset still uses a link token (only signup/verify moved to a
    6-digit code) — pull it from the logged dev email body."""
    for record in reversed(caplog.records):
        if marker in record.message:
            match = re.search(r"token=([A-Za-z0-9_\-]+)", record.message)
            if match:
                return match.group(1)
    return None


def _extract_code_from_log(caplog, marker):
    """The dev email fallback logs the email body (including the code) via
    logging_config.logger — pull the code out of the most recent matching
    log record instead of needing a real inbox."""
    for record in reversed(caplog.records):
        if marker in record.message:
            match = re.search(r"verification code is: (\d{6})", record.message)
            if match:
                return match.group(1)
    return None


# ── Email verification ────────────────────────────────────────────────────

def test_new_account_starts_unverified(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.get("/me", headers=auth)
    assert r.json()["email_verified"] is False


def test_verify_email_with_valid_token(client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="ai_analyst")

    r = client.post("/auth/signup", json={"email": "verify@example.com", "password": "supersecret123"})
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    code = _extract_code_from_log(caplog, "verify@example.com")
    assert code, "verification code should have been logged"

    r = client.post("/auth/verify-email", json={"email": "verify@example.com", "code": code})
    assert r.status_code == 200
    assert r.json()["verified"] is True

    r = client.get("/me", headers=auth)
    assert r.json()["email_verified"] is True


def test_verify_email_with_bad_token_rejected(client):
    r = client.post("/auth/verify-email", json={"email": "nope@example.com", "code": "000000"})
    assert r.status_code == 400


def test_resend_verification_for_already_verified_account(client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="ai_analyst")

    r = client.post("/auth/signup", json={"email": "verify2@example.com", "password": "supersecret123"})
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    code = _extract_code_from_log(caplog, "verify2@example.com")
    client.post("/auth/verify-email", json={"email": "verify2@example.com", "code": code})

    r = client.post("/auth/resend-verification", headers=auth)
    assert r.status_code == 200
    assert r.json()["already_verified"] is True


# ── Password reset ─────────────────────────────────────────────────────────

def test_password_reset_flow_end_to_end(client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="ai_analyst")

    client.post("/auth/signup", json={"email": "reset@example.com", "password": "oldpassword123"})

    r = client.post("/auth/request-password-reset", json={"email": "reset@example.com"})
    assert r.status_code == 200

    token = _extract_token_from_log(caplog, "reset@example.com")
    assert token, "reset link should have been logged"

    r = client.post("/auth/reset-password", json={"token": token, "new_password": "newpassword456"})
    assert r.status_code == 200

    r = client.post("/auth/login", json={"email": "reset@example.com", "password": "oldpassword123"})
    assert r.status_code == 401

    r = client.post("/auth/login", json={"email": "reset@example.com", "password": "newpassword456"})
    assert r.status_code == 200


def test_password_reset_request_for_unknown_email_still_returns_200(client):
    # Prevents user enumeration — same response whether or not the account exists.
    r = client.post("/auth/request-password-reset", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert r.json()["sent"] is True


def test_password_reset_with_bad_token_rejected(client):
    r = client.post("/auth/reset-password", json={"token": "garbage", "new_password": "whatever123"})
    assert r.status_code == 400


# ── Admin ────────────────────────────────────────────────────────────────

def test_admin_endpoints_reject_normal_users(client, signed_up_user):
    auth, _ = signed_up_user
    assert client.get("/admin/users", headers=auth).status_code == 403
    assert client.post("/admin/users/x/grant", json={"plan": "starter"}, headers=auth).status_code == 403
    assert client.post("/admin/users/x/revoke", headers=auth).status_code == 403


def test_owner_account_has_admin_access(client):
    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/admin/users", headers=owner_auth)
    assert r.status_code == 200


def test_admin_can_list_users(client, signed_up_user):
    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get("/admin/users", headers=owner_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(u["email"] == "test@example.com" for u in body["items"])


def test_admin_can_grant_access_without_payment(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.get("/me", headers=auth)
    user_email = r.json()["email"]

    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    users = client.get("/admin/users", headers=owner_auth).json()["items"]
    target_id = next(u["id"] for u in users if u["email"] == user_email)

    r = client.post(f"/admin/users/{target_id}/grant", json={"plan": "pro"}, headers=owner_auth)
    assert r.status_code == 200
    assert r.json()["plan"] == "pro"

    # the granted user can now analyze without ever paying
    r = client.post("/analyze", json={"question": "granted access test", "dataset_id": "ds1"}, headers=auth)
    assert r.status_code == 200


def test_admin_can_revoke_access(client, subscribed_user):
    r = client.get("/me", headers=subscribed_user)
    user_email = r.json()["email"]

    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    users = client.get("/admin/users", headers=owner_auth).json()["items"]
    target_id = next(u["id"] for u in users if u["email"] == user_email)

    r = client.post(f"/admin/users/{target_id}/revoke", headers=owner_auth)
    assert r.status_code == 200

    r = client.post("/analyze", json={"question": "should be blocked", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 402


def test_self_service_cancel(client, subscribed_user):
    r = client.post("/billing/cancel", headers=subscribed_user)
    assert r.status_code == 200

    r = client.get("/me", headers=subscribed_user)
    assert r.json()["subscription"] is None

    r = client.post("/analyze", json={"question": "should be blocked", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 402


def test_admin_refund_calls_paymob_and_revokes_access(client, subscribed_user, monkeypatch):
    import paymob
    monkeypatch.setattr(paymob, "refund_transaction", lambda paymob_transaction_id, amount_cents: {"success": True})

    r = client.get("/me", headers=subscribed_user)
    user_email = r.json()["email"]

    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    users = client.get("/admin/users", headers=owner_auth).json()["items"]
    target_id = next(u["id"] for u in users if u["email"] == user_email)

    r = client.post(f"/admin/users/{target_id}/refund", headers=owner_auth)
    assert r.status_code == 200
    assert r.json()["refunded"] is True

    r = client.post("/analyze", json={"question": "should be blocked", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 402


def test_admin_refund_with_no_payment_returns_400(client, signed_up_user):
    auth, email = signed_up_user
    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    users = client.get("/admin/users", headers=owner_auth).json()["items"]
    target_id = next(u["id"] for u in users if u["email"] == email)

    r = client.post(f"/admin/users/{target_id}/refund", headers=owner_auth)
    assert r.status_code == 400


# ── Report pagination ───────────────────────────────────────────────────

def test_reports_pagination_shape(client, subscribed_user):
    for i in range(3):
        client.post("/analyze", json={"question": f"q{i}", "dataset_id": "ds1"}, headers=subscribed_user)

    r = client.get("/reports?limit=2&offset=0", headers=subscribed_user)
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert len(body["items"]) == 2

    r = client.get("/reports?limit=2&offset=2", headers=subscribed_user)
    body = r.json()
    assert len(body["items"]) == 1


def test_reports_limit_is_capped(client, subscribed_user):
    r = client.get("/reports?limit=99999", headers=subscribed_user)
    assert r.json()["limit"] == 100
