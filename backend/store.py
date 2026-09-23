"""SQLite snapshots and atomic, append-only uploads/completions."""

import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from backend.engine import RecommendationEngine
from backend.loader import Dataset, DatasetValidationError, HISTORY_COLUMNS, validate_dataset
from backend.schemas import Completion, UploadBatch


class StoreError(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class Store:
    def __init__(self, path: str):
        if path == ":memory:":
            raise ValueError("The API requires a persistent SQLite file inside storage/")
        self.path = path
        self._migrate_assessments()

    def _migrate_assessments(self):
        """Undo the old materialized API gains once; history becomes the source of truth.

        Old completion responses retain each previous level, so reversing them
        restores the assessment even for capped and recurring activities.
        """
        with self.transaction(write=True) as connection:
            if connection.execute("SELECT 1 FROM metadata WHERE key = 'skill_storage_version'").fetchone():
                return
            for row in connection.execute("SELECT * FROM completion_requests ORDER BY rowid DESC").fetchall():
                result = json.loads(row["response"])
                employee_row = connection.execute("SELECT payload FROM employees WHERE employee_id = ?", (row["employee_id"],)).fetchone()
                employee = json.loads(employee_row["payload"])
                for change in result["skill_changes"]:
                    employee["skills"][change["skill_id"]] = change["before"]
                connection.execute("UPDATE employees SET payload = ? WHERE employee_id = ?", (json.dumps(employee), row["employee_id"]))
            connection.execute("INSERT INTO metadata (key, value) VALUES ('skill_storage_version', '2')")

    @contextmanager
    def transaction(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=1)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _read(connection) -> Dataset:
        metadata = {row["key"]: json.loads(row["value"]) for row in connection.execute("SELECT * FROM metadata")}
        collections = {
            table: [json.loads(row["payload"]) for row in connection.execute(f"SELECT payload FROM {table}")]
            for table in ("employees", "events", "skills", "role_profiles")
        }
        return Dataset(
            meta=metadata["dataset_meta"], proficiency_scale=metadata["proficiency_scale"],
            activity_history=[dict(row) for row in connection.execute("SELECT * FROM activity_history")],
            completion_record_ids=[json.loads(row["response"])["record_id"] for row in connection.execute(
                "SELECT response FROM completion_requests ORDER BY rowid"
            )],
            **collections,
        )

    def read(self) -> Dataset:
        with self.transaction() as connection:
            return self._read(connection)

    @staticmethod
    def _insert_history(connection, records):
        connection.executemany(
            f"INSERT INTO activity_history ({', '.join(HISTORY_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in HISTORY_COLUMNS)})",
            [tuple(row[column] for column in HISTORY_COLUMNS) for row in records],
        )

    def upload(self, batch: UploadBatch) -> dict:
        payload = batch.model_dump(mode="json")
        employees, history = payload["employees"], payload["activity_history"]
        with self.transaction(write=True) as connection:
            dataset = self._read(connection)
            snapshot = dataset.meta["skills"]["as_of_date"]
            if batch.meta is not None and batch.meta.get("as_of_date") != snapshot:
                raise DatasetValidationError([f"meta.as_of_date must match snapshot {snapshot}"])
            for rows, existing, key in (
                (employees, dataset.employees, "employee_id"),
                (history, dataset.activity_history, "record_id"),
            ):
                seen = {row[key] for row in existing}
                for row in rows:
                    if row[key] in seen:
                        raise StoreError(409, f"Duplicate {key}: {row[key]}")
                    seen.add(row[key])
            dataset.employees.extend(employees)
            dataset.activity_history.extend(history)
            # Validate the merged graph: managers and history may refer to this same batch.
            validate_dataset(dataset)
            connection.executemany(
                "INSERT INTO employees (employee_id, role, grade, manager_id, payload) VALUES (?, ?, ?, ?, ?)",
                [(row["employee_id"], row["role"], row["grade"], row["manager_id"], json.dumps(row)) for row in employees],
            )
            self._insert_history(connection, history)
            return {
                "inserted": {"employees": len(employees), "activity_history": len(history)},
                "employee_ids": [row["employee_id"] for row in employees], "reference_errors": 0,
            }

    def complete(self, request: Completion) -> dict:
        with self.transaction(write=True) as connection:
            saved = connection.execute(
                "SELECT * FROM completion_requests WHERE request_id = ?", (request.request_id,)
            ).fetchone()
            if saved:
                if (saved["employee_id"], saved["event_id"]) != (request.employee_id, request.event_id):
                    raise StoreError(409, "request_id already used for a different completion")
                return json.loads(saved["response"])
            dataset = self._read(connection)
            engine = RecommendationEngine(dataset)
            if request.employee_id not in engine.employees:
                raise StoreError(404, "Employee not found")
            if request.event_id not in engine.events:
                raise StoreError(404, "Event not found")
            evaluated = next(row for row in engine.evaluate(request.employee_id) if row["event_id"] == request.event_id)
            if not evaluated["eligible"]:
                raise StoreError(409, {"message": "Event is ineligible", "reasons": evaluated["exclusion_reasons"]})
            employee = engine.employees[request.employee_id]
            changes = []
            for gain in engine.events[request.event_id]["develops_skills"]:
                skill_id = gain["skill_id"]
                before = employee["skills"].get(skill_id, 0)
                after = before + max(0, min(gain["gain"], gain["max_level"] - before))
                changes.append({"skill_id": skill_id, "before": before, "after": after, "gain": after - before})
            record = {
                "record_id": f"API_{uuid4().hex}", "employee_id": request.employee_id,
                "event_id": request.event_id, "date": engine.as_of.isoformat(), "due_date": None,
                "status": "completed", "completion_pct": 100, "score": None,
                "feedback_rating": None, "assigned_by": "self",
            }
            self._insert_history(connection, [record])
            dataset.activity_history.append(record)
            dataset.completion_record_ids.append(record["record_id"])
            updated = RecommendationEngine(dataset)
            response = {
                "employee_id": request.employee_id, "event_id": request.event_id,
                "request_id": request.request_id, "record_id": record["record_id"],
                "skills": updated.employees[request.employee_id]["skills"], "skill_changes": changes,
                "trajectory": updated.trajectory(request.employee_id),
            }
            connection.execute(
                "INSERT INTO completion_requests (request_id, employee_id, event_id, response) VALUES (?, ?, ?, ?)",
                (request.request_id, request.employee_id, request.event_id, json.dumps(response)),
            )
            return response
