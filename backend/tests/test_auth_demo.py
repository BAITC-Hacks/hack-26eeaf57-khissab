"""Jury entry points retain the same session and authorization boundaries."""

import hashlib
import hmac
import re
import time

import pytest
from fastapi.testclient import TestClient

from backend.auth import SESSION_SECONDS
from backend.main import create_app
from backend.tests.test_api import api, complete, new_profile


@pytest.fixture
def demo_api(api, monkeypatch):
    client, _, settings = api
    assert client.post("/upload", json={"employees": [new_profile("E0002")]}).status_code == 201
    monkeypatch.setenv("AUTH_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "local")
    app = create_app(**settings)
    with TestClient(app) as demo:
        yield demo, app, settings


def demo_sign_in(client, account):
    response = client.post("/auth/demo/login", json={"account": account})
    assert response.status_code == 200, response.text
    session = response.json()
    client.headers["Authorization"] = "Bearer " + session["access_token"]
    return session


def test_demo_employee_has_only_fixed_profile_and_normal_permissions(demo_api):
    client, app, _ = demo_api
    assert client.get("/auth/demo").json() == {"enabled": True, "employee_id": "E0002"}
    assert client.get("/employees").status_code == 401
    session = demo_sign_in(client, "employee")
    assert session["user"] == {"username": "employee:E0002", "role": "employee", "employee_id": "E0002"}
    assert session["token_type"] == "bearer"
    assert SESSION_SECONDS - 2 <= session["expires_at"] - time.time() <= SESSION_SECONDS
    assert client.get("/auth/me").json() == session["user"]
    assert [employee["id"] for employee in client.get("/employees").json()] == ["E0002"]
    assert client.get("/employees/E0002").status_code == 200
    assert client.get("/recommend/E0002").status_code == 200
    for path in ("/employees/TEST_EMPLOYEE", "/recommend/TEST_EMPLOYEE", "/hr/overview"):
        assert client.get(path).status_code == 403
    before = app.state.store.read()
    assert complete(client).status_code == 403
    assert client.post("/upload", json={"employees": [new_profile()]}).status_code == 403
    assert app.state.store.read() == before
    assert complete(client, employee_id="E0002").status_code == 200


def test_demo_hr_can_review_all_profiles_and_upload(demo_api):
    client, _, _ = demo_api
    session = demo_sign_in(client, "hr")
    assert session["user"] == {"username": "hr", "role": "hr", "employee_id": None}
    assert len(client.get("/employees").json()) == 2
    assert client.get("/hr/overview").status_code == 200
    assert client.post("/upload", json={"employees": [new_profile("JURY_UPLOAD")]}).status_code == 201
    assert client.get("/employees/JURY_UPLOAD").status_code == 200


@pytest.mark.parametrize("body", [
    {"account": "employee", "employee_id": "TEST_EMPLOYEE"},
    {"account": "employee", "username": "hr"},
    {"account": "employee", "role": "hr"},
    {"account": "TEST_EMPLOYEE"},
    {"account": "employee:TEST_EMPLOYEE"},
    {},
])
def test_demo_rejects_arbitrary_identity_and_role_fields(demo_api, body):
    client, app, _ = demo_api
    with app.state.store.transaction() as connection:
        before = connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0]
    assert client.post("/auth/demo/login", json=body).status_code == 422
    with app.state.store.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == before


@pytest.mark.parametrize("demo_mode,environment,enabled", [
    (None, "local", False),
    ("false", "local", False),
    ("0", "local", False),
    ("true", None, False),
    ("true", "production", False),
    ("yes", "local", True),
    ("1", "local", True),
])
def test_demo_requires_explicit_enablement_in_local_environment(api, monkeypatch, demo_mode, environment, enabled):
    _, _, settings = api
    for key, value in (("AUTH_DEMO_MODE", demo_mode), ("APP_ENV", environment)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    with TestClient(create_app(**settings)) as client:
        assert client.get("/auth/demo").json() == {"enabled": enabled, "employee_id": None}
        assert client.post("/auth/demo/login", json={"account": "hr"}).status_code == (200 if enabled else 404)
        # No fallback to the only available employee when E0002 is absent.
        assert client.post("/auth/demo/login", json={"account": "employee"}).status_code == 404
        assert client.get("/auth/demo").headers["cache-control"] == "no-store"


def test_demo_sessions_are_hashed_persistent_revocable_and_expiring(demo_api, monkeypatch):
    client, app, settings = demo_api
    session = demo_sign_in(client, "employee")
    with app.state.store.transaction() as connection:
        rows = connection.execute("SELECT token_hash FROM auth_sessions").fetchall()
        assert session["access_token"] not in {row["token_hash"] for row in rows}
        assert hashlib.sha256(session["access_token"].encode()).hexdigest() in {row["token_hash"] for row in rows}
    with TestClient(create_app(**settings)) as restarted:
        restarted.headers["Authorization"] = "Bearer " + session["access_token"]
        assert restarted.get("/auth/me").status_code == 200
        assert restarted.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401
    demo_sign_in(client, "hr")
    with app.state.store.transaction(write=True) as connection:
        connection.execute("UPDATE auth_sessions SET expires_at = 0")
    assert client.get("/hr/overview").status_code == 401


@pytest.mark.parametrize("mode,environment", [("false", "local"), ("true", "production")])
def test_disabling_demo_rejects_demo_sessions_but_keeps_private_sessions(demo_api, monkeypatch, mode, environment):
    client, app, settings = demo_api
    demo_session = demo_sign_in(client, "hr")
    private_session = client.post("/auth/login", json=app.state.auth.credentials("hr")).json()
    monkeypatch.setenv("AUTH_DEMO_MODE", mode)
    monkeypatch.setenv("APP_ENV", environment)
    # A running instance retains its startup settings until it is restarted.
    assert client.get("/auth/demo").json()["enabled"] is True
    with TestClient(create_app(**settings)) as restarted:
        assert restarted.get("/auth/demo").json()["enabled"] is False
        restarted.headers["Authorization"] = "Bearer " + demo_session["access_token"]
        assert restarted.get("/auth/me").status_code == 401
        assert restarted.get("/hr/overview").status_code == 401
        restarted.headers["Authorization"] = "Bearer " + private_session["access_token"]
        assert restarted.get("/auth/me").status_code == 200


def test_legacy_session_schema_migrates_without_losing_private_sessions(api, monkeypatch):
    client, app, settings = api
    session = client.post("/auth/login", json=app.state.auth.credentials("hr")).json()
    with app.state.store.transaction(write=True) as connection:
        connection.execute("ALTER TABLE auth_sessions RENAME TO auth_sessions_new")
        connection.execute("""CREATE TABLE auth_sessions (
            token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL,
            employee_id TEXT, expires_at REAL NOT NULL)""")
        connection.execute("""INSERT INTO auth_sessions SELECT token_hash, username, role,
            employee_id, expires_at FROM auth_sessions_new""")
        connection.execute("DROP TABLE auth_sessions_new")
    monkeypatch.setenv("AUTH_DEMO_MODE", "false")
    for _ in range(2):
        with TestClient(create_app(**settings)) as restarted:
            restarted.headers["Authorization"] = "Bearer " + session["access_token"]
            assert restarted.get("/auth/me").status_code == 200
            with restarted.app.state.store.transaction() as connection:
                assert {row["is_demo"] for row in connection.execute("SELECT is_demo FROM auth_sessions")} == {0}


@pytest.mark.parametrize("username", ["TEST_EMPLOYEE", " employee:TEST_EMPLOYEE ", "EMPLOYEE:TEST_EMPLOYEE"])
def test_employee_id_alias_accepts_short_case_insensitive_code(api, username):
    client, app, _ = api
    credentials = app.state.auth.credentials("TEST_EMPLOYEE")
    assert credentials["username"] == "employee:TEST_EMPLOYEE"
    assert re.fullmatch(r"[A-F0-9]{10}", credentials["access_code"])
    response = client.post("/auth/login", json={"username": username, "access_code": credentials["access_code"].lower()})
    assert response.status_code == 200
    assert response.json()["user"]["employee_id"] == "TEST_EMPLOYEE"
    assert response.json()["user"]["username"] == "employee:TEST_EMPLOYEE"
    assert client.post("/auth/login", json={"username": "test_employee", "access_code": credentials["access_code"]}).status_code == 401


@pytest.mark.parametrize("username", [" HR ", "hr", "Hr"])
def test_hr_username_alias_and_existing_long_code_remain_valid(api, username):
    client, app, _ = api
    legacy_code = hmac.new(app.state.auth.key, b"career-quest-login:hr", hashlib.sha256).hexdigest()
    for code in (legacy_code, legacy_code.upper(), app.state.auth.credentials("HR")["access_code"]):
        response = client.post("/auth/login", json={"username": username, "access_code": code})
        assert response.status_code == 200
        assert response.json()["user"]["username"] == "hr"


@pytest.mark.parametrize("aliases", [
    ["hr", "HR", " hr ", "Hr", "hR", " HR "],
    ["TEST_EMPLOYEE", "employee:TEST_EMPLOYEE", " TEST_EMPLOYEE ",
     "EMPLOYEE:TEST_EMPLOYEE", " Employee:TEST_EMPLOYEE ", "TEST_EMPLOYEE"],
])
def test_login_aliases_share_attempt_limit(api, aliases):
    client, app, _ = api
    for alias in aliases[:5]:
        assert client.post("/auth/login", json={"username": alias, "access_code": "wrong"}).status_code == 401
    blocked = client.post("/auth/login", json={"username": aliases[-1], "access_code": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    # Knowing the real code does not bypass the existing account lockout.
    assert client.post("/auth/login", json=app.state.auth.credentials(aliases[-1])).status_code == 429
