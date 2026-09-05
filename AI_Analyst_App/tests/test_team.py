def test_unsubscribed_user_cannot_access_team_endpoints(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.get("/team/members", headers=auth)
    assert r.status_code == 402


def test_starter_plan_cannot_use_team_endpoints(client, signed_up_user):
    from tests.conftest import _activate_subscription

    auth, email = signed_up_user
    _activate_subscription(client, auth, email, "starter")

    r = client.get("/team/members", headers=auth)
    assert r.status_code == 402


def test_pro_owner_can_invite_list_and_remove_members(client, subscribed_user, signed_up_user_factory):
    r = client.get("/team/members", headers=subscribed_user)
    assert r.status_code == 200
    assert r.json()["used_seats"] == 1
    assert r.json()["members"] == []

    teammate_auth, teammate_email = signed_up_user_factory("teammate@example.com")

    r = client.post("/team/invite", json={"email": teammate_email}, headers=subscribed_user)
    assert r.status_code == 200

    r = client.get("/team/members", headers=subscribed_user)
    body = r.json()
    assert body["used_seats"] == 2
    assert body["members"][0]["email"] == teammate_email

    # the teammate now rides on the owner's plan without their own subscription
    r = client.get("/me", headers=teammate_auth)
    me = r.json()
    assert me["subscription"] is not None
    assert me["subscription"]["plan"] == "pro"
    assert me["team_role"] == "member"

    member_id = body["members"][0]["id"]
    r = client.delete(f"/team/members/{member_id}", headers=subscribed_user)
    assert r.status_code == 200

    r = client.get("/me", headers=teammate_auth)
    assert r.json()["subscription"] is None


def test_invite_requires_existing_account(client, subscribed_user):
    r = client.post("/team/invite", json={"email": "nobody@example.com"}, headers=subscribed_user)
    assert r.status_code == 404


def test_invite_rejects_seat_cap_overflow(client, subscribed_user, signed_up_user_factory, monkeypatch):
    import config
    monkeypatch.setitem(config.PLANS["pro"], "max_seats", 2)

    teammate_auth, teammate_email = signed_up_user_factory("seat2@example.com")
    r = client.post("/team/invite", json={"email": teammate_email}, headers=subscribed_user)
    assert r.status_code == 200

    other_auth, other_email = signed_up_user_factory("seat3@example.com")
    r = client.post("/team/invite", json={"email": other_email}, headers=subscribed_user)
    assert r.status_code == 400


def test_team_member_cannot_invite_others(client, subscribed_user, signed_up_user_factory):
    teammate_auth, teammate_email = signed_up_user_factory("member-only@example.com")
    client.post("/team/invite", json={"email": teammate_email}, headers=subscribed_user)

    r = client.post("/team/invite", json={"email": "someone-else@example.com"}, headers=teammate_auth)
    assert r.status_code == 400


def test_cannot_invite_self(client, subscribed_user):
    r = client.post("/team/invite", json={"email": "test@example.com"}, headers=subscribed_user)
    assert r.status_code == 400


def test_remove_nonmember_404s(client, subscribed_user):
    r = client.delete("/team/members/not-a-real-id", headers=subscribed_user)
    assert r.status_code == 404
