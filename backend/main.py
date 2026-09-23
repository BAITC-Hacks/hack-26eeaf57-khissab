"""Career Quest HTTP API. Scoring and SQLite work never wait on the optional LLM."""

import os
import sqlite3
from collections import Counter, defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.engine import RecommendationEngine
from backend.auth import Auth, DemoLogin, Login, allow_employee, bearer, current_user, hr_user
from backend.explain import LLMSettings, explain_recommendations, slim_factors
from backend.loader import DatasetValidationError, load_dataset
from backend.schemas import Completion, UploadBatch
from backend.store import Store, StoreError
from backend.uploads import read_upload


DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def create_app(*, data_dir=None, database_url=None, llm_settings=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        result = await run_in_threadpool(load_dataset, data_dir, database_url)
        app.state.store = Store(result["database"])
        app.state.auth = Auth(app.state.store)
        app.state.llm_settings = llm_settings if llm_settings is not None else LLMSettings.from_env()
        yield

    app = FastAPI(title="Career Quest API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[value.strip() for value in os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if value.strip()],
        allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/auth/login")
    def login(body: Login):
        return app.state.auth.login(body)

    @app.get("/auth/demo")
    def demo_status():
        return app.state.auth.demo_status()

    @app.post("/auth/demo/login")
    def demo_login(body: DemoLogin):
        return app.state.auth.demo_login(body)

    @app.get("/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.post("/auth/logout")
    def logout(user=Depends(current_user), credentials=Depends(bearer)):
        app.state.auth.logout(credentials.credentials)
        return {"status": "signed_out"}

    @app.exception_handler(DatasetValidationError)
    async def invalid_dataset(request, exc):
        return JSONResponse(status_code=422, content={"detail": exc.errors})

    @app.exception_handler(StoreError)
    async def store_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return JSONResponse(status_code=503, content={"detail": "Database busy; retry shortly"}, headers={"Retry-After": "1"})
        return JSONResponse(status_code=500, content={"detail": "Database operation failed"})

    def employee_engine(employee_id):
        engine = RecommendationEngine(app.state.store.read())
        if employee_id not in engine.employees:
            raise HTTPException(404, "Employee not found")
        return engine

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/employees")
    def employees(user=Depends(current_user)) -> list[dict]:
        return [{
            "id": row["employee_id"], "name": row["full_name"], "role": row["role"],
            "grade": row["grade"], "department": row["department"],
        } for row in sorted(app.state.store.read().employees, key=lambda row: row["employee_id"])
            if user["role"] == "hr" or row["employee_id"] == user["employee_id"]]

    @app.get("/employees/{employee_id}")
    def employee(employee_id: str, user=Depends(current_user)) -> dict:
        allow_employee(user, employee_id)
        dataset = app.state.store.read()
        engine = RecommendationEngine(dataset)
        if employee_id not in engine.employees:
            raise HTTPException(404, "Employee not found")
        history = [{
            **row, "title": engine.events[row["event_id"]]["title"],
            "type": engine.events[row["event_id"]]["type"],
        } for row in engine.history[employee_id]]
        return {
            "profile": engine.employees[employee_id], "trajectory": engine.trajectory(employee_id),
            "as_of_date": engine.as_of.isoformat(),
            "assessed_skills": engine.assessed_skills[employee_id],
            "skill_updates": engine.skill_updates[employee_id],
            "activity_history": sorted(history, key=lambda row: (row["date"], row["record_id"]), reverse=True),
        }

    @app.get("/recommend/{employee_id}")
    async def recommend(employee_id: str, limit: int = Query(3, ge=1, le=3), debug: bool = False,
                        user=Depends(current_user)) -> dict:
        allow_employee(user, employee_id)
        engine = await run_in_threadpool(employee_engine, employee_id)
        ranked = await run_in_threadpool(engine.recommend, employee_id, limit)
        explained = await explain_recommendations(ranked, app.state.llm_settings)
        steps = []
        for row in explained:
            event = engine.events[row["event_id"]]
            explanation = row["explanation"]
            step = {
                "event_id": row["event_id"], "title": row["title"], "type": row["type"],
                "format": event["format"], "duration_hours": event["duration_hours"],
                "upcoming_sessions": event["upcoming_sessions"], "score": row["score"],
                "factors": slim_factors(row), "rationale": explanation["text"],
                "explanation": {key: value for key, value in explanation.items() if key != "text"},
                "gateway_to": row["factors"]["gateway_to"],
            }
            if debug:
                step["debug_factors"] = row["factors"]
            steps.append(step)
        return {"employee_id": employee_id, "as_of_date": engine.as_of.isoformat(), "recommendations": steps}

    @app.post("/complete")
    def complete(body: Completion, user=Depends(current_user)) -> dict:
        allow_employee(user, body.employee_id)
        return app.state.store.complete(body)

    @app.post("/upload", status_code=201, openapi_extra={"requestBody": {
        "required": True, "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/UploadBatch"}},
            "multipart/form-data": {"schema": {"type": "object", "properties": {
                "employees_file": {"type": "string", "format": "binary"},
                "history_file": {"type": "string", "format": "binary"},
            }}},
        },
    }})
    async def upload(request: Request, user=Depends(hr_user)) -> dict:
        """Accept {meta?, employees: [...], activity_history: [...]} JSON, or
        multipart employees_file (dataset employees.json) and history_file (CSV).
        Both collections are optional, but the batch must contain at least one row.
        """
        batch = await read_upload(request)
        return await run_in_threadpool(app.state.store.upload, batch)

    @app.get("/hr/overview")
    def hr_overview(user=Depends(hr_user)) -> dict:
        engine = RecommendationEngine(app.state.store.read())
        lagging = defaultdict(lambda: {"total_gap": 0, "employees_affected": 0, "critical_employees": 0})
        without_step = []
        for employee_id, employee in sorted(engine.employees.items()):
            trajectory = engine.trajectory(employee_id)
            if not engine.recommend(employee_id):
                without_step.append({
                    "employee_id": employee_id, "name": employee["full_name"],
                    "role": employee["role"], "grade": employee["grade"], "department": employee["department"],
                    "target_role": trajectory["target_role"], "target_grade": trajectory["target_grade"],
                    "total_gap": trajectory["total_gap"], "critical_gap": trajectory["critical_gap"],
                    "reason": "target_met" if trajectory["total_gap"] == 0 else "no_eligible_useful_activity",
                })
            for skill in engine.trajectory(employee_id)["skills"]:
                if skill["gap"] > 0:
                    aggregate = lagging[skill["skill_id"]]
                    aggregate["total_gap"] += skill["gap"]
                    aggregate["employees_affected"] += 1
                    aggregate["critical_employees"] += skill["critical"]
        by_event = defaultdict(list)
        for records in engine.history.values():
            for record in records:
                by_event[record["event_id"]].append(record)
        participation = []
        for event_id, event in sorted(engine.events.items()):
            records = by_event[event_id]
            participation.append({
                "event_id": event_id, "title": event["title"], "type": event["type"],
                "records": len(records), "participants": len({row["employee_id"] for row in records}),
                "status_counts": dict(Counter(row["status"] for row in records)),
            })
        return {
            "as_of_date": engine.as_of.isoformat(), "employee_count": len(engine.employees),
            "employees_without_recommendation": {"count": len(without_step), "employees": without_step},
            "most_lagging_skills": sorted([
                {"skill_id": key, "skill_name": engine.skill_names[key], **value}
                for key, value in lagging.items()
            ], key=lambda row: (-row["total_gap"], row["skill_id"])),
            "participation_by_activity": participation,
        }

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            upload_schema = UploadBatch.model_json_schema(ref_template="#/components/schemas/{model}")
            schemas = schema.setdefault("components", {}).setdefault("schemas", {})
            schemas.update(upload_schema.pop("$defs", {}))
            schemas["UploadBatch"] = upload_schema
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app


app = create_app()
