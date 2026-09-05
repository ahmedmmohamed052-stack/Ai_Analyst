import datetime


def test_start_trial_requires_no_card(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/start-trial", json={"plan": "growth"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "growth"
    assert body["status"] == "trial"

    r = client.get("/me", headers=auth)
    me = r.json()
    assert me["subscription"]["status"] == "trial"
    assert me["subscription"]["plan"] == "growth"
    assert me["trial_used"] is True


def test_trial_grants_access_to_analyze(client, signed_up_user):
    auth, _ = signed_up_user
    client.post("/billing/start-trial", json={"plan": "starter"}, headers=auth)
    r = client.post("/analyze", json={"question": "q1", "dataset_id": "ds1"}, headers=auth)
    assert r.status_code == 200


def test_trial_limits_are_lower_than_paid_limits(client, signed_up_user):
    """Starter trial = 1/day, same as starter's paid limit — growth/pro trials
    are intentionally lower than their paid limits (2 vs 5, 3 vs 20)."""
    auth, _ = signed_up_user
    client.post("/billing/start-trial", json={"plan": "growth"}, headers=auth)

    r1 = client.post("/analyze", json={"question": "q1", "dataset_id": "ds1"}, headers=auth)
    r2 = client.post("/analyze", json={"question": "q2", "dataset_id": "ds1"}, headers=auth)
    r3 = client.post("/analyze", json={"question": "q3", "dataset_id": "ds1"}, headers=auth)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429  # growth trial allows 2/day, not growth's paid 5/day


def test_only_one_trial_per_account_ever(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/start-trial", json={"plan": "starter"}, headers=auth)
    assert r.status_code == 200

    r = client.post("/billing/start-trial", json={"plan": "pro"}, headers=auth)
    assert r.status_code == 400


def test_cannot_start_trial_with_active_paid_subscription(client, subscribed_user):
    r = client.post("/billing/start-trial", json={"plan": "starter"}, headers=subscribed_user)
    assert r.status_code == 400


def test_start_trial_rejects_unknown_plan(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post("/billing/start-trial", json={"plan": "enterprise"}, headers=auth)
    assert r.status_code == 400


def test_trials_endpoint_lists_terms(client):
    r = client.get("/trials")
    assert r.status_code == 200
    body = r.json()
    assert body["starter"]["trial_days"] == 14
    assert body["growth"]["trial_days"] == 14
    assert body["pro"]["trial_days"] == 14
    assert body["starter"]["trial_analyze_per_day"] == 1
    assert body["growth"]["trial_analyze_per_day"] == 2
    assert body["pro"]["trial_analyze_per_day"] == 3
    assert body["growth"]["convert_bonus_days"] == 7
    assert body["pro"]["convert_bonus_days"] == 14
    assert body["starter"]["convert_bonus_days"] == 0


def test_trial_conversion_grants_bonus_days_for_growth(client, signed_up_user):
    from tests.conftest import _activate_subscription

    auth, email = signed_up_user
    client.post("/billing/start-trial", json={"plan": "growth"}, headers=auth)

    _activate_subscription(client, auth, email, "growth")

    r = client.get("/me", headers=auth)
    expires_at = r.json()["subscription"]["expires_at"]
    import utils
    days_left = (utils.parse_iso(expires_at) - utils.utcnow()).days
    # 30-day plan + 7 bonus days for converting from the growth trial == ~37
    assert 35 <= days_left <= 37


def test_trial_conversion_grants_bonus_days_for_pro(client, signed_up_user):
    from tests.conftest import _activate_subscription

    auth, email = signed_up_user
    client.post("/billing/start-trial", json={"plan": "pro"}, headers=auth)

    _activate_subscription(client, auth, email, "pro")

    r = client.get("/me", headers=auth)
    expires_at = r.json()["subscription"]["expires_at"]
    import utils
    days_left = (utils.parse_iso(expires_at) - utils.utcnow()).days
    # 30-day plan + 14 bonus days for converting from the pro trial == ~44
    assert 42 <= days_left <= 44


def test_starter_conversion_has_no_bonus(client, signed_up_user):
    from tests.conftest import _activate_subscription

    auth, email = signed_up_user
    client.post("/billing/start-trial", json={"plan": "starter"}, headers=auth)

    _activate_subscription(client, auth, email, "starter")

    r = client.get("/me", headers=auth)
    expires_at = r.json()["subscription"]["expires_at"]
    import utils
    days_left = (utils.parse_iso(expires_at) - utils.utcnow()).days
    assert 28 <= days_left <= 30


def test_bonus_not_reapplied_on_renewal(client, signed_up_user):
    """The conversion bonus is one-time — renewing the same plan again later
    shouldn't stack another bonus on top."""
    from tests.conftest import _activate_subscription
    import utils

    auth, email = signed_up_user
    client.post("/billing/start-trial", json={"plan": "growth"}, headers=auth)
    _activate_subscription(client, auth, email, "growth")

    r = client.get("/me", headers=auth)
    first_expiry = utils.parse_iso(r.json()["subscription"]["expires_at"])

    _activate_subscription(client, auth, email, "growth")
    r = client.get("/me", headers=auth)
    second_expiry = utils.parse_iso(r.json()["subscription"]["expires_at"])

    # second renewal should add ~30 days (no bonus), not ~37
    delta_days = (second_expiry - first_expiry).days
    assert 29 <= delta_days <= 30


def test_no_bonus_when_converting_to_a_different_tier_than_trialed(client, signed_up_user):
    from tests.conftest import _activate_subscription
    import utils

    auth, email = signed_up_user
    client.post("/billing/start-trial", json={"plan": "growth"}, headers=auth)
    _activate_subscription(client, auth, email, "pro")  # different tier than trialed

    r = client.get("/me", headers=auth)
    days_left = (utils.parse_iso(r.json()["subscription"]["expires_at"]) - utils.utcnow()).days
    assert 28 <= days_left <= 30  # plain 30-day pro, no growth or pro bonus


def test_trial_user_cannot_use_team_endpoints(client, signed_up_user):
    auth, _ = signed_up_user
    client.post("/billing/start-trial", json={"plan": "pro"}, headers=auth)
    r = client.get("/team/members", headers=auth)
    assert r.status_code == 402