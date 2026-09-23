import json

from fastapi.testclient import TestClient

from backend.engine import RecommendationEngine
from backend.main import create_app
from backend.store import Store
from backend.tests.test_api import api, complete, new_profile, sign_in
from backend.tests.test_engine import SYSTEM, SPEAKING, record


def test_anonymous_routes_and_employee_horizontal_vertical_permissions(api):
    client, app, _ = api
    assert client.post("/upload", json={"employees": [new_profile("OTHER")]}).status_code == 201
    client.headers.pop("Authorization")
    for path in ("/employees", "/employees/TEST_EMPLOYEE", "/recommend/TEST_EMPLOYEE?debug=true", "/hr/overview", "/auth/me"):
        assert client.get(path).status_code == 401
    assert complete(client).status_code == 401
    assert client.post("/upload", json={"employees": [new_profile()]}).status_code == 401
    session = sign_in(client, "employee:TEST_EMPLOYEE")
    assert session["user"]["role"] == "employee"
    assert [r["id"] for r in client.get("/employees").json()] == ["TEST_EMPLOYEE"]
    assert client.get("/employees/TEST_EMPLOYEE").status_code == 200
    assert client.get("/recommend/TEST_EMPLOYEE").status_code == 200
    for path in ("/employees/OTHER", "/recommend/OTHER?debug=true", "/hr/overview"):
        assert client.get(path).status_code == 403
    before = app.state.store.read()
    assert complete(client, employee_id="OTHER").status_code == 403
    assert client.post("/upload", json={"employees": [new_profile()]}).status_code == 403
    assert app.state.store.read() == before
    assert complete(client).status_code == 200


def test_access_codes_are_identity_bound_sessions_expire_and_logout_revokes(api):
    client, app, settings = api
    own = app.state.auth.credentials("employee:TEST_EMPLOYEE")
    assert client.post("/auth/login", json={**own, "username": "hr"}).status_code == 401
    assert client.post("/auth/login", json={**own, "role": "hr"}).status_code == 422
    result = sign_in(client, "employee:TEST_EMPLOYEE")
    with TestClient(create_app(**settings)) as restarted:
        restarted.headers["Authorization"] = "Bearer " + result["access_token"]
        assert restarted.get("/auth/me").status_code == 200
        assert restarted.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401
    sign_in(client)
    with app.state.store.transaction(write=True) as c:
        c.execute("UPDATE auth_sessions SET expires_at = 0")
    assert client.get("/employees").status_code == 401
    client.headers["Authorization"] = "Bearer forged-hr"
    assert client.get("/hr/overview").status_code == 401


def test_login_failure_limit_and_private_cache_headers(api):
    client, _, _ = api
    assert client.get("/employees").headers["cache-control"] == "no-store"
    for _ in range(5):
        assert client.post("/auth/login", json={"username": "hr", "access_code": "wrong"}).status_code == 401
    response = client.post("/auth/login", json={"username": "hr", "access_code": "wrong"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_history_upload_applies_gain_once_and_enables_step_after_restart(api):
    client, app, settings = api
    initial = app.state.store.read().employees[0]["skills"][SYSTEM]
    rows = [record("IMPORTED", "CRITICAL", date="2026-09-02")]
    assert client.post("/upload", json={"activity_history": rows}).status_code == 201
    for _ in range(2):
        detail = client.get("/employees/TEST_EMPLOYEE").json()
        assert detail["profile"]["skills"][SYSTEM] == initial + 1
        assert detail["assessed_skills"][SYSTEM] == initial
        assert detail["skill_updates"][0]["record_id"] == "IMPORTED"
    assert app.state.store.read().employees[0]["skills"][SYSTEM] == initial
    with TestClient(create_app(**settings)) as restarted:
        sign_in(restarted)
        assert restarted.get("/employees/TEST_EMPLOYEE").json() == detail


def test_completion_on_assessment_day_is_applied_once_and_backdated_upload_replays(api):
    client, app, settings = api
    with app.state.store.transaction(write=True) as c:
        emp = new_profile("TEST_EMPLOYEE")
        emp["last_review_date"] = "2026-10-01"
        c.execute("UPDATE employees SET payload = ?", (json.dumps(emp),))
    result = complete(client).json()
    assert result["skills"][SYSTEM] == 3
    assert complete(client).json() == result
    assert client.get("/employees/TEST_EMPLOYEE").json()["profile"]["skills"][SYSTEM] == 3
    with TestClient(create_app(**settings)) as restarted:
        sign_in(restarted)
        assert restarted.get("/employees/TEST_EMPLOYEE").json()["profile"]["skills"][SYSTEM] == 3


def test_legacy_materialized_gains_migrate_once_without_losing_progress(api):
    client, app, _ = api
    first = complete(client, event_id="EV_036").json()
    second = complete(client, event_id="EV_036", request_id="repeat").json()
    assert second["skills"][SPEAKING] == 2
    with app.state.store.transaction(write=True) as c:
        emp = new_profile("TEST_EMPLOYEE")
        emp["skills"] = second["skills"]
        c.execute("UPDATE employees SET payload = ?", (json.dumps(emp),))
        c.execute("DELETE FROM metadata WHERE key = 'skill_storage_version'")
    for _ in range(2):
        migrated = Store(app.state.store.path)
        raw = migrated.read()
        assert raw.employees[0]["skills"][SPEAKING] == 0
        assert RecommendationEngine(raw).employees["TEST_EMPLOYEE"]["skills"][SPEAKING] == 2
        assert len(raw.completion_record_ids) == 2
    assert complete(client, event_id="EV_036").json() == first


def test_backdated_import_after_live_completion_and_chronological_cap_order(api):
    client, app, _ = api
    complete(client, event_id="EV_036")
    # CAPPED raises speaking to at most one, then the later live club adds one.
    assert client.post("/upload", json={"activity_history": [record("EARLIER", "CAPPED", date="2026-09-10")]}).status_code == 201
    assert client.get("/employees/TEST_EMPLOYEE").json()["profile"]["skills"][SPEAKING] == 2
    assert app.state.store.read().employees[0]["skills"][SPEAKING] == 0
