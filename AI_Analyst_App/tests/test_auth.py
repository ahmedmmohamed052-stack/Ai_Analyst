def test_signup_creates_account_and_returns_token(client):
    r = client.post("/auth/signup", json={"email": "a@example.com", "password": "supersecret123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "supersecret123"})
    r = client.post("/auth/signup", json={"email": "a@example.com", "password": "different"})
    assert r.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "supersecret123"})
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_login_correct_password_succeeds(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "supersecret123"})
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "supersecret123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_protected_route_without_token_rejected(client):
    r = client.get("/me")
    assert r.status_code == 401


def test_protected_route_with_garbage_token_rejected(client):
    r = client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_reflects_new_account_with_no_subscription(client, signed_up_user):
    auth, email = signed_up_user
    r = client.get("/me", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == email
    assert body["subscription"] is None


def test_dev_password_logs_in_as_owner(client):
    r = client.post("/auth/login", json={"password": "letmein"})
    assert r.status_code == 200
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/me", headers=auth)
    assert r.json()["is_owner"] is True


def test_wrong_dev_password_falls_through_to_normal_login_error(client):
    r = client.post("/auth/login", json={"password": "totally-wrong"})
    assert r.status_code == 401
