def test_analyze_returns_full_pipeline_shape(client, subscribed_user):
    r = client.post("/analyze", json={"question": "Why did revenue decrease?", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 200
    body = r.json()
    for key in (
        "report_id", "business_context", "sql_query", "quality_interpretation",
        "statistics_interpretation", "correlation_interpretation", "trend_interpretation",
        "outlier_interpretation", "more_analysis_interpretation", "eda",
        "root_cause", "insights", "recommendations",
    ):
        assert key in body, f"missing {key}"


def test_analyze_rejects_empty_question(client, subscribed_user):
    r = client.post("/analyze", json={"question": "   ", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 400


def test_analyze_persists_report_visible_in_history(client, subscribed_user):
    r = client.post("/analyze", json={"question": "Why did revenue decrease?", "dataset_id": "ds1"}, headers=subscribed_user)
    report_id = r.json()["report_id"]

    r = client.get("/reports", headers=subscribed_user)
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert report_id in ids


def test_report_pdf_downloads_for_owner_of_report(client, subscribed_user):
    r = client.post("/analyze", json={"question": "Why did revenue decrease?", "dataset_id": "ds1"}, headers=subscribed_user)
    report_id = r.json()["report_id"]

    r = client.get(f"/report/{report_id}/pdf", headers=subscribed_user)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 0


def test_report_pdf_not_accessible_by_other_users(client, subscribed_user):
    r = client.post("/analyze", json={"question": "Why did revenue decrease?", "dataset_id": "ds1"}, headers=subscribed_user)
    report_id = r.json()["report_id"]

    r = client.post("/auth/signup", json={"email": "other@example.com", "password": "supersecret123"})
    other_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get(f"/report/{report_id}/pdf", headers=other_auth)
    assert r.status_code == 404


def test_report_pdf_missing_id_returns_404(client, subscribed_user):
    r = client.get("/report/does-not-exist/pdf", headers=subscribed_user)
    assert r.status_code == 404


def test_rate_limit_blocks_after_max_analyze_per_day(client, subscribed_user, monkeypatch):
    import config
    monkeypatch.setitem(config.PLANS["pro"], "analyze_per_day", 2)

    r1 = client.post("/analyze", json={"question": "q1", "dataset_id": "ds1"}, headers=subscribed_user)
    r2 = client.post("/analyze", json={"question": "q2", "dataset_id": "ds1"}, headers=subscribed_user)
    r3 = client.post("/analyze", json={"question": "q3", "dataset_id": "ds1"}, headers=subscribed_user)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_owner_account_bypasses_rate_limit(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "DEFAULT_ANALYZE_PER_DAY", 1)

    r = client.post("/auth/login", json={"password": "letmein"})
    owner_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    for _ in range(3):
        r = client.post("/analyze", json={"question": "q", "dataset_id": "ds1"}, headers=owner_auth)
        assert r.status_code == 200


def test_users_only_see_their_own_reports(client):
    r = client.post("/auth/signup", json={"email": "u1@example.com", "password": "supersecret123"})
    u1_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/auth/signup", json={"email": "u2@example.com", "password": "supersecret123"})
    u2_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # give u1 a subscription and run one analysis
    _activate_subscription(client, u1_auth, "u1@example.com")
    client.post("/analyze", json={"question": "u1 question", "dataset_id": "ds1"}, headers=u1_auth)

    r = client.get("/reports", headers=u2_auth)
    assert r.json()["items"] == []


def _activate_subscription(client, auth, email):
    import hashlib
    import hmac

    import paymob

    r = client.post("/billing/checkout", json={"plan": "starter"}, headers=auth)
    checkout = r.json()

    fake_db = client.app.state.fake_db
    user = fake_db.get_user_by_email(email)
    txn = fake_db.get_transaction(user.id, checkout["transaction_id"])
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
    client.post(f"/payments/paymob/webhook?hmac={computed_hmac}", json={"obj": webhook_obj})
