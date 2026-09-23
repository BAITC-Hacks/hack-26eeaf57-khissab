import asyncio
import copy
import csv
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from time import perf_counter
from threading import Event
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.explain import LLMSettings
from backend.loader import HISTORY_COLUMNS, ROOT
from backend.main import create_app
from backend.tests.test_engine import SPEAKING, SYSTEM, adversarial_dataset, event, record
from backend.tests.test_explain import tool_response
from backend.uploads import MAX_UPLOAD_BYTES


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HISTORY_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


@pytest.fixture
def api(tmp_path):
    data = adversarial_dataset()
    data.events.extend([
        event("EV_036", SPEAKING, type="meetup"),
        event("LOCKED", prerequisites={SYSTEM: 4}),
        event("WRONG_GRADE", target_grades=["Lead"]),
        event("MANDATORY", mandatory=True),
        event("WRONG_ROLE", target_roles=[]),
        event("CAPPED", develops_skills=[
            {"skill_id": SYSTEM, "gain": 2, "max_level": 1},
            {"skill_id": SPEAKING, "gain": 2, "max_level": 1},
        ]),
    ])
    meta = data.meta["skills"]
    directory = tmp_path / "data"
    directory.mkdir()
    for name, document in {
        "employees": {"meta": meta, "employees": data.employees},
        "events": {"meta": meta, "events": data.events},
        "skills": {"meta": meta, "skills": data.skills, "role_profiles": data.role_profiles,
                   "proficiency_scale": data.proficiency_scale},
    }.items():
        (directory / f"{name}.json").write_text(json.dumps(document))
    (directory / "activity_history.csv").write_bytes(csv_bytes(data.activity_history))
    settings = {"data_dir": directory, "database_url": f"sqlite:///{tmp_path / 'storage' / 'test.sqlite3'}",
                "llm_settings": LLMSettings()}
    app = create_app(**settings)
    with TestClient(app) as client:
        yield client, app, settings


def new_profile(employee_id="DEMO_NEW"):
    profile = copy.deepcopy(adversarial_dataset().employees[0])
    return {**profile, "employee_id": employee_id, "full_name": "Demo New Profile"}


def complete(client, event_id="CRITICAL", request_id="complete-1", employee_id="TEST_EMPLOYEE"):
    return client.post("/complete", json={
        "employee_id": employee_id, "event_id": event_id, "request_id": request_id,
    })


def test_profiles_trajectory_and_cors(api):
    client, _, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    employees = client.get("/employees").json()
    assert set(employees[0]) == {"id", "name", "role", "grade", "department"}
    detail = client.get("/employees/TEST_EMPLOYEE").json()
    assert detail["profile"]["skills"][SYSTEM] == 2
    trajectory = detail["trajectory"]
    assert trajectory["target_grade"] == "Senior"
    assert trajectory["total_gap"] == 11
    assert trajectory["critical_gap"] == 2
    assert next(s for s in trajectory["skills"] if s["skill_id"] == SYSTEM)["critical"]
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options("/complete", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    response = client.options("/upload", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    schema = client.get("/openapi.json").json()
    upload = schema["paths"]["/upload"]["post"]["requestBody"]["content"]
    assert set(upload) == {"application/json", "multipart/form-data"}
    assert "Employee" in schema["components"]["schemas"]


def test_recommendation_slim_default_debug_full_and_trap(api):
    client, _, _ = api
    with patch("backend.explain._call_model", side_effect=AssertionError("No network")):
        response = client.get("/recommend/TEST_EMPLOYEE")
    assert response.status_code == 200
    rows = response.json()["recommendations"]
    assert "CRITICAL" in {row["event_id"] for row in rows}
    assert "LOWEST_SKILL" not in {row["event_id"] for row in rows}
    assert len(rows) == 3
    for row in rows:
        assert "engagement_by_type" not in row["factors"]
        assert "debug_factors" not in row
        assert row["factors"]["engagement"]["type"] == row["type"]
        assert row["rationale"]
        assert row["explanation"]["source"] == "template"
        assert len(row["explanation"]["validated_fact_ids"]) >= 3
        assert row["gateway_to"] == row["factors"]["gateway_to"]
    debug = client.get("/recommend/TEST_EMPLOYEE?debug=true&limit=1").json()["recommendations"]
    assert len(debug) == 1
    assert debug[0]["debug_factors"]["engagement_by_type"]["workshop"]["skip_count"] == 3
    for limit in (0, 4, "abc"):
        assert client.get(f"/recommend/TEST_EMPLOYEE?limit={limit}").status_code == 422


@pytest.mark.parametrize("environment", [
    {},
    {"LLM_MODEL": "local-test-model", "LLM_BASE_URL": "http://localhost:11434/v1"},
    {"LLM_MODEL": "local-test-model", "LLM_BASE_URL": "http://localhost:11434/v1", "LLM_API_KEY": ""},
], ids=["no-llm-settings", "key-omitted", "key-empty"])
def test_startup_without_llm_key_uses_template(api, monkeypatch, environment):
    _, _, settings = api
    for name in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    app = create_app(**{**settings, "llm_settings": None})
    with patch("backend.explain._call_model", side_effect=AssertionError("No-key path must stay offline")) as model:
        with TestClient(app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            response = client.get("/recommend/TEST_EMPLOYEE")
            assert response.status_code == 200, response.text
            rows = response.json()["recommendations"]
            assert rows
            assert all(row["explanation"]["source"] == "template" for row in rows)
            assert all(row["explanation"]["fallback_reason"] == "no_api_key" for row in rows)
        model.assert_not_called()


def test_employee_history_has_event_details_all_statuses_and_no_other_employees(api):
    client, app, _ = api
    statuses = ("completed", "in_progress", "dropped", "no_show", "declined", "overdue")
    event_ids = ("CRITICAL", "SQL", "PAST_WORKSHOP_0", "PAST_WORKSHOP_1", "PAST_WORKSHOP_2", "MANDATORY")
    history = [record(
        f"HISTORY_{index}", event_id, status, "manager", employee_id="WITH_HISTORY",
        date="2026-09-21" if index % 2 else "2026-09-20",
        completion_pct=100 if status == "completed" else 50 if status in ("in_progress", "dropped", "overdue") else 0,
    ) for index, (status, event_id) in enumerate(zip(statuses, event_ids))]
    response = client.post("/upload", json={
        "employees": [new_profile("WITH_HISTORY"), new_profile("EMPTY_HISTORY")], "activity_history": history,
    })
    assert response.status_code == 201, response.text
    detail = client.get("/employees/WITH_HISTORY").json()
    assert detail["as_of_date"] == "2026-10-01"
    events = {row["event_id"]: row for row in app.state.store.read().events}
    expected = [{**row, "title": events[row["event_id"]]["title"], "type": events[row["event_id"]]["type"]}
                for row in sorted(history, key=lambda row: (row["date"], row["record_id"]), reverse=True)]
    assert detail["activity_history"] == expected
    assert {row["status"] for row in detail["activity_history"]} == set(statuses)
    assert client.get("/employees/EMPTY_HISTORY").json()["activity_history"] == []
    original = client.get("/employees/TEST_EMPLOYEE").json()["activity_history"]
    assert {row["record_id"] for row in original} == {"SKIP_0", "SKIP_1", "SKIP_2"}
    assert all(row["employee_id"] == "TEST_EMPLOYEE" for row in original)


def test_upload_json_then_immediate_recommendation_and_restart(api):
    client, app, settings = api
    profile = new_profile()
    history = [record("NEW_SKIP", "PAST_WORKSHOP_0", "declined", "manager", employee_id=profile["employee_id"])]
    response = client.post("/upload", json={"employees": [profile], "activity_history": history})
    assert response.status_code == 201, response.text
    assert response.json() == {
        "inserted": {"employees": 1, "activity_history": 1}, "employee_ids": ["DEMO_NEW"], "reference_errors": 0,
    }
    result = client.get("/recommend/DEMO_NEW").json()
    workshop = next(row for row in result["recommendations"] if row["type"] == "workshop")
    assert workshop["factors"]["engagement"]["skip_count"] == 1
    assert workshop["factors"]["engagement"]["multiplier"] == 0.6
    assert any(row["id"] == "DEMO_NEW" for row in client.get("/employees").json())
    with TestClient(create_app(**settings)) as restarted:
        assert restarted.get("/recommend/DEMO_NEW").json() == result
    assert len(app.state.store.read().employees) == 2


def test_upload_multipart_same_batch_manager_history_and_assessed_skills(api):
    client, _, _ = api
    lead = {**new_profile("DEMO_LEAD"), "grade": "Lead", "career_goal": None}
    employee = {**new_profile(), "manager_id": "DEMO_LEAD"}
    history = [record("NEW_COMPLETION", "CRITICAL", employee_id="DEMO_NEW")]
    response = client.post("/upload", files={
        "employees_file": ("../../employees.json", json.dumps({
            "meta": {"as_of_date": "2026-10-01"}, "employees": [employee, lead],
        }), "application/json"),
        "history_file": ("history.csv", csv_bytes(history), "text/csv"),
    })
    assert response.status_code == 201, response.text
    assert response.json()["inserted"] == {"employees": 2, "activity_history": 1}
    detail = client.get("/employees/DEMO_NEW").json()
    assert detail["profile"]["skills"] == employee["skills"]  # Uploaded history never replays gains.
    assert "CRITICAL" not in {r["event_id"] for r in client.get("/recommend/DEMO_NEW").json()["recommendations"]}


@pytest.mark.parametrize("field,value", [
    ("manager_id", "MISSING"), ("role", "MISSING"), ("grade", "MISSING"),
    ("skills", {"UNKNOWN_SKILL": 2}), ("career_goal", {"target_role": "MISSING", "target_grade": "Senior"}),
])
def test_upload_invalid_employee_refs_roll_back(api, field, value):
    client, app, _ = api
    before = app.state.store.read()
    profile = {**new_profile(), field: value}
    response = client.post("/upload", json={"employees": [new_profile("VALID"), profile]})
    assert response.status_code == 422, response.text
    assert app.state.store.read() == before
    assert client.get("/employees/VALID").status_code == 404


@pytest.mark.parametrize("field", ["employee_id", "event_id"])
def test_upload_invalid_history_refs_roll_back(api, field):
    client, app, _ = api
    before = app.state.store.read()
    history = record("BAD", "CRITICAL", employee_id="DEMO_NEW")
    history[field] = "MISSING"
    response = client.post("/upload", json={"employees": [new_profile()], "activity_history": [history]})
    assert response.status_code == 422
    assert f"activity_history[BAD].{field}" in response.text
    assert app.state.store.read() == before


def test_upload_conflicts_and_malformed_inputs_leave_database_unchanged(api):
    client, app, _ = api
    before = app.state.store.read()
    cases = [
        ({}, 422),
        ({"employees": [new_profile("TEST_EMPLOYEE")]}, 409),
        ({"employees": [new_profile(), new_profile()]}, 409),
        ({"activity_history": [record("SKIP_0", "CRITICAL")]}, 409),
        ({"meta": {"as_of_date": "2025-01-01"}, "employees": [new_profile()]}, 422),
        ({"employees": [{**new_profile(), "hire_date": "nonsense"}]}, 422),
        ({"employees": [{**new_profile(), "skills": {SYSTEM: True}}]}, 422),
        ({"activity_history": [record("BAD", "CRITICAL", completion_pct=0)]}, 422),
        ({"employees": [new_profile()], "events": []}, 422),
    ]
    for payload, code in cases:
        assert client.post("/upload", json=payload).status_code == code
    assert client.post("/upload", content='{"employees": [], "employees": []}',
                       headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/upload", content="bad", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/upload", content="bad", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/upload", files={"history_file": ("h.csv", "bad,header\n")}).status_code == 422
    assert client.post("/upload", files={"unexpected": ("h.csv", csv_bytes([]))}).status_code == 422
    assert client.post("/upload", content=b" " * (MAX_UPLOAD_BYTES + 1),
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert app.state.store.read() == before


def test_history_only_upload_updates_engagement(api):
    client, _, _ = api
    response = client.post("/upload", files={"history_file": ("h.csv", csv_bytes([
        record("NEW_HISTORY", "PAST_WORKSHOP_0", "no_show", "manager"),
    ]), "text/csv")})
    assert response.status_code == 201
    factors = client.get("/recommend/TEST_EMPLOYEE?debug=true").json()["recommendations"][0]["debug_factors"]
    assert factors["engagement_by_type"]["workshop"]["skip_count"] == 4


def test_complete_updates_trajectory_is_idempotent_and_survives_restart(api):
    client, app, settings = api
    response = complete(client)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["skills"][SYSTEM] == 3
    assert updated["trajectory"]["critical_gap"] == 1
    assert updated["trajectory"]["total_gap"] == 10
    assert updated["skill_changes"] == [{"skill_id": SYSTEM, "before": 2, "after": 3, "gain": 1}]
    assert complete(client).json() == updated
    assert complete(client, request_id="different-request").status_code == 409
    assert complete(client, event_id="SQL").status_code == 409
    stored = app.state.store.read()
    completions = [row for row in stored.activity_history if row["event_id"] == "CRITICAL"]
    assert len(completions) == 1
    assert completions[0]["date"] == "2026-10-01"
    with TestClient(create_app(**settings)) as restarted:
        assert complete(restarted).json() == updated
        detail = restarted.get("/employees/TEST_EMPLOYEE").json()
        assert detail["profile"]["skills"] == updated["skills"]
        assert detail["profile"]["grade"] == "Middle"
        history = detail["activity_history"]
        assert len(history) == 4
        assert history[0] == {**completions[0], "title": "CRITICAL", "type": "course"}
        assert history[0]["record_id"] == updated["record_id"]
        assert "CRITICAL" not in {r["event_id"] for r in restarted.get("/recommend/TEST_EMPLOYEE").json()["recommendations"]}


def test_complete_caps_gains_without_reducing_above_cap_skills(api):
    client, _, _ = api
    result = complete(client, event_id="CAPPED").json()
    assert result["skills"][SYSTEM] == 2
    assert result["skills"][SPEAKING] == 1
    assert result["skill_changes"][0]["gain"] == 0


def test_repeatable_completion_and_concurrent_retry(api):
    client, app, _ = api
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: complete(client, event_id="EV_036"), range(2)))
    assert [row.status_code for row in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert results[0].json()["skills"][SPEAKING] == 1
    assert complete(client, event_id="EV_036", request_id="second-session").json()["skills"][SPEAKING] == 2
    records = [r for r in app.state.store.read().activity_history if r["event_id"] == "EV_036"]
    assert len(records) == 2
    history = client.get("/employees/TEST_EMPLOYEE").json()["activity_history"]
    assert {r["record_id"] for r in history if r["event_id"] == "EV_036"} == {r["record_id"] for r in records}


@pytest.mark.parametrize("event_id,reason", [
    ("LOCKED", "unmet_prerequisites"), ("WRONG_GRADE", "wrong_grade"),
    ("MANDATORY", "mandatory"), ("WRONG_ROLE", "wrong_role"),
])
def test_complete_rechecks_all_hard_filters(api, event_id, reason):
    client, app, _ = api
    before = app.state.store.read()
    response = complete(client, event_id=event_id)
    assert response.status_code == 409
    assert reason in response.json()["detail"]["reasons"]
    assert app.state.store.read() == before


def test_transaction_rolls_back_skill_and_history_on_sql_failure(api):
    client, app, _ = api
    before = app.state.store.read()
    with closing(sqlite3.connect(app.state.store.path)) as connection, connection:
        connection.execute("""CREATE TRIGGER fail_completion BEFORE INSERT ON completion_requests
            BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="test rollback"):
        complete(client)
    assert app.state.store.read() == before


def test_unknown_ids_and_missing_request_id(api):
    client, _, _ = api
    assert client.get("/employees/unknown").status_code == 404
    assert client.get("/recommend/unknown").status_code == 404
    assert complete(client, employee_id="unknown").status_code == 404
    assert complete(client, event_id="unknown").status_code == 404
    assert client.post("/complete", json={"employee_id": "TEST_EMPLOYEE", "event_id": "CRITICAL"}).status_code == 422


def test_mocked_model_path_and_rejected_numbers_at_api_boundary(api):
    client, app, _ = api
    app.state.llm_settings = LLMSettings(model="mock-only", base_url="http://localhost:1234/v1", api_key="test")

    async def model(settings, body, transport):
        return tool_response(body)

    with patch("backend.explain._call_model", model):
        rows = client.get("/recommend/TEST_EMPLOYEE").json()["recommendations"]
    assert all(r["explanation"]["source"] == "llm" for r in rows)

    async def invented(settings, body, transport):
        result = tool_response(body)
        function = result["choices"][0]["message"]["tool_calls"][0]["function"]
        plan = json.loads(function["arguments"])
        plan["invented_score"] = 999
        function["arguments"] = json.dumps(plan)
        return result

    with patch("backend.explain._call_model", invented):
        rows = client.get("/recommend/TEST_EMPLOYEE").json()["recommendations"]
    assert all(r["explanation"]["fallback_reason"] == "invalid_model_response" for r in rows)
    assert all("999" not in r["rationale"] for r in rows)


def test_slow_model_times_out_concurrently_without_blocking_profiles(api):
    client, app, _ = api
    app.state.llm_settings = LLMSettings(base_url="http://localhost:1234/v1", api_key="test", timeout_seconds=0.2)
    started = Event()
    cancelled = []

    async def slow_model(settings, body, transport):
        started.set()
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)

    with patch("backend.explain._call_model", slow_model), ThreadPoolExecutor(max_workers=1) as pool:
        start = perf_counter()
        future = pool.submit(client.get, "/recommend/TEST_EMPLOYEE")
        assert started.wait(1)
        assert client.get("/employees").status_code == 200
        assert not future.done()
        result = future.result(timeout=2)
        assert perf_counter() - start < 1
    assert len(cancelled) == 3
    assert all(row["explanation"]["fallback_reason"] == "timeout" for row in result.json()["recommendations"])


def test_hr_is_aggregate_only_and_includes_new_no_step_profile(api):
    client, _, _ = api
    profile = new_profile("NO_STEP")
    profile["skills"] = {key: 5 for key in profile["skills"]}
    assert client.post("/upload", json={"employees": [profile]}).status_code == 201
    assert client.get("/recommend/NO_STEP").json()["recommendations"] == []
    before = client.get("/hr/overview").json()
    assert before["employee_count"] == 2
    assert before["employees_without_recommendation"] == {"count": 1}
    assert before["most_lagging_skills"][0]["total_gap"] == 5
    complete(client)
    after = client.get("/hr/overview").json()
    system = next(s for s in after["most_lagging_skills"] if s["skill_id"] == SYSTEM)
    assert system["total_gap"] == 1
    activity = next(a for a in after["participation_by_activity"] if a["event_id"] == "CRITICAL")
    assert activity["status_counts"] == {"completed": 1}
    assert activity["participants"] == 1
    for forbidden in ("employee_id", "TEST_EMPLOYEE", "NO_STEP", "full_name", "engagement", "assigned_by", "record_id"):
        assert forbidden not in json.dumps(after)


@pytest.mark.skipif(not (ROOT / "data" / "employees.json").exists(), reason="Starter kit not installed")
def test_real_dataset_e0002_gateway_completion_and_endpoint_budgets(tmp_path):
    app = create_app(data_dir=ROOT / "data", database_url=f"sqlite:///{tmp_path / 'api.sqlite3'}", llm_settings=LLMSettings())
    with TestClient(app) as client:
        for path in ("/employees", "/employees/E0002", "/recommend/E0002", "/hr/overview"):
            start = perf_counter()
            response = client.get(path)
            assert response.status_code == 200, response.text
            assert perf_counter() - start < 2, path
        rows = client.get("/recommend/E0002").json()["recommendations"]
        first = rows[0]
        assert first["event_id"] == "EV_005"
        assert first["score"] == pytest.approx(2.808)
        assert first["factors"]["engagement"]["multiplier"] == pytest.approx(0.468)
        assert {g["event_id"] for g in first["gateway_to"]} == {"EV_006", "EV_007"}
        result = complete(client, employee_id="E0002", event_id="EV_005").json()
        assert result["skills"][SYSTEM] == 2
        updated = client.get("/recommend/E0002").json()["recommendations"]
        assert "EV_005" not in {r["event_id"] for r in updated}
        assert {"EV_006", "EV_007"} & {r["event_id"] for r in updated}
        response = client.post("/upload", files={
            "employees_file": ("employees.json", (ROOT / "examples/trap_employees.json").read_bytes(), "application/json"),
            "history_file": ("history.csv", (ROOT / "examples/trap_activity_history.csv").read_bytes(), "text/csv"),
        })
        assert response.status_code == 201, response.text
        assert response.json()["inserted"] == {"employees": 1, "activity_history": 3}
        rows = client.get("/recommend/DEMO_TRAP?debug=true").json()["recommendations"]
        assert rows[0]["event_id"] == "EV_005"
        assert rows[0]["score"] == 6
        assert "EV_011" not in {row["event_id"] for row in rows}
        assert rows[0]["debug_factors"]["engagement_by_type"]["workshop"]["skip_count"] == 3
