import io

import pandas as pd


def test_upload_csv_creates_dataset(client, signed_up_user):
    auth, _ = signed_up_user
    csv_bytes = b"order_date,revenue,region\n2024-01-01,100,North\n2024-01-02,200,South\n"
    r = client.post(
        "/datasets/upload",
        data={"name": "My Sales"},
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "My Sales"
    assert body["source_type"] == "file"
    assert body["row_count"] == 2
    assert {c["name"] for c in body["columns"]} == {"order_date", "revenue", "region"}


def test_upload_rejects_unsupported_extension(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post(
        "/datasets/upload",
        data={"name": "bad"},
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth,
    )
    assert r.status_code == 400


def test_upload_rejects_empty_file(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post(
        "/datasets/upload",
        data={"name": "empty"},
        files={"file": ("empty.csv", io.BytesIO(b"a,b\n"), "text/csv")},
        headers=auth,
    )
    assert r.status_code == 400


def test_list_datasets_only_shows_own(client, signed_up_user):
    auth, _ = signed_up_user
    csv_bytes = b"a,b\n1,2\n"
    client.post(
        "/datasets/upload", data={"name": "d1"},
        files={"file": ("d1.csv", io.BytesIO(csv_bytes), "text/csv")}, headers=auth,
    )

    r = client.post("/auth/signup", json={"email": "other-ds@example.com", "password": "supersecret123"})
    other_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get("/datasets", headers=other_auth)
    assert r.json() == []

    r = client.get("/datasets", headers=auth)
    assert len(r.json()) == 1
    assert "encrypted_password" not in r.json()[0]


def test_delete_dataset(client, signed_up_user):
    auth, _ = signed_up_user
    csv_bytes = b"a,b\n1,2\n"
    r = client.post(
        "/datasets/upload", data={"name": "to-delete"},
        files={"file": ("d.csv", io.BytesIO(csv_bytes), "text/csv")}, headers=auth,
    )
    dataset_id = r.json()["id"]

    r = client.delete(f"/datasets/{dataset_id}", headers=auth)
    assert r.status_code == 200

    r = client.get("/datasets", headers=auth)
    assert r.json() == []


def test_delete_missing_dataset_404s(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.delete("/datasets/does-not-exist", headers=auth)
    assert r.status_code == 404


def test_connect_database_rejects_bad_db_type(client, signed_up_user):
    auth, _ = signed_up_user
    r = client.post(
        "/datasets/connect",
        json={
            "name": "x", "db_type": "sqlserver", "host": "h", "port": 1433,
            "database": "d", "user": "u", "password": "p",
        },
        headers=auth,
    )
    assert r.status_code == 400


def test_connect_database_tests_connection_before_saving(client, signed_up_user, monkeypatch):
    """With no real database reachable in tests, a real connection attempt
    should fail fast with a 400, not silently save bad credentials."""
    auth, _ = signed_up_user
    r = client.post(
        "/datasets/connect",
        json={
            "name": "x", "db_type": "postgres", "host": "definitely-not-a-real-host.invalid",
            "port": 5432, "database": "d", "user": "u", "password": "p",
        },
        headers=auth,
    )
    assert r.status_code == 400

    r = client.get("/datasets", headers=auth)
    assert r.json() == []


def test_connect_database_succeeds_and_never_returns_password(client, signed_up_user, monkeypatch):
    import main

    monkeypatch.setattr(main, "test_external_connection", lambda *a, **kw: None)

    auth, _ = signed_up_user
    r = client.post(
        "/datasets/connect",
        json={
            "name": "Prod DB", "db_type": "postgres", "host": "db.example.com",
            "port": 5432, "database": "app", "user": "svc", "password": "hunter2",
        },
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source_type"] == "external_db"
    assert "password" not in body
    assert "encrypted_password" not in body
