"""Validate the local starter kit and seed SQLite without resetting progress."""

import argparse
import csv
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GRADES = ("Junior", "Middle", "Senior", "Lead")
HISTORY_COLUMNS = (
    "record_id", "employee_id", "event_id", "date", "due_date", "status",
    "completion_pct", "score", "feedback_rating", "assigned_by",
)
TABLES = ("employees", "events", "skills", "activity_history", "role_profiles")


class DatasetValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Dataset validation failed:\n" + "\n".join(errors))


@dataclass
class Dataset:
    meta: dict
    proficiency_scale: dict
    skills: list[dict]
    role_profiles: list[dict]
    employees: list[dict]
    events: list[dict]
    activity_history: list[dict]


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def read_dataset(data_dir: str | Path) -> Dataset:
    """Read JSON wrappers and convert nullable CSV numbers to int/None."""
    directory = Path(data_dir)
    documents = {}
    for name, collections in (
        ("skills", ("skills", "role_profiles")),
        ("employees", ("employees",)),
        ("events", ("events",)),
    ):
        path = directory / f"{name}.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        except (OSError, ValueError) as exc:
            raise DatasetValidationError([f"{path}: {exc}"]) from exc
        if not isinstance(document, dict) or not isinstance(document.get("meta"), dict):
            raise DatasetValidationError([f"{path}: expected an object with meta"])
        for collection in collections:
            rows = document.get(collection)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise DatasetValidationError([f"{path}.{collection}: expected an array of objects"])
        documents[name] = document

    errors = []
    snapshot = documents["skills"]["meta"].get("as_of_date")
    try:
        date.fromisoformat(snapshot)
    except (TypeError, ValueError):
        errors.append("skills.json.meta.as_of_date: expected an ISO date")
    for name, document in documents.items():
        if document["meta"].get("as_of_date") != snapshot:
            errors.append(f"{name}.json.meta.as_of_date: snapshot differs from skills.json")
    scale = documents["skills"].get("proficiency_scale")
    if not isinstance(scale, dict) or set(scale) != {str(level) for level in range(6)}:
        errors.append("skills.json.proficiency_scale: expected levels 0-5")

    history = []
    path = directory / "activity_history.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if (reader.fieldnames is None or len(reader.fieldnames) != len(HISTORY_COLUMNS)
                    or set(reader.fieldnames) != set(HISTORY_COLUMNS)):
                raise DatasetValidationError([f"{path}: expected columns {', '.join(HISTORY_COLUMNS)}"])
            for line, row in enumerate(reader, start=2):
                location = f"activity_history.csv:{line} ({row.get('record_id')})"
                if None in row or None in row.values():
                    errors.append(f"{location}: wrong number of columns")
                    continue
                for field in ("completion_pct", "score", "feedback_rating"):
                    try:
                        row[field] = None if row[field] == "" and field != "completion_pct" else int(row[field])
                    except ValueError:
                        errors.append(f"{location}.{field}: expected an integer")
                row["due_date"] = row["due_date"] or None
                history.append(row)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DatasetValidationError([f"{path}: {exc}"]) from exc
    if errors:
        raise DatasetValidationError(errors)
    return Dataset(
        meta={name: document["meta"] for name, document in documents.items()},
        proficiency_scale=scale,
        skills=documents["skills"]["skills"],
        role_profiles=documents["skills"]["role_profiles"],
        employees=documents["employees"]["employees"],
        events=documents["events"]["events"],
        activity_history=history,
    )


def validate_dataset(dataset: Dataset) -> None:
    """Check IDs and every relation, collecting errors before any database write."""
    errors = []

    def mapping(value, location):
        if not isinstance(value, dict):
            errors.append(f"{location}: expected an object")
            return {}
        return value

    def sequence(value, location):
        if not isinstance(value, list):
            errors.append(f"{location}: expected an array")
            return []
        return value

    def index(rows, fields, label):
        result = {}
        for offset, row in enumerate(rows):
            key = tuple(row.get(field) for field in fields)
            if any(not isinstance(value, str) or not value.strip() for value in key):
                errors.append(f"{label}[{offset}]: expected nonempty {', '.join(fields)}")
            elif key in result:
                errors.append(f"{label}: duplicate ID {key}")
            else:
                result[key] = row
        return result

    def reference(value, catalog, location):
        if not isinstance(value, str) or value not in catalog:
            errors.append(f"{location}: unknown reference {value!r}")

    def number(value, minimum, maximum, location, integer=False):
        types = (int,) if integer else (int, float)
        if type(value) not in types or not minimum <= value <= maximum:
            errors.append(f"{location}: expected {'integer' if integer else 'number'} in [{minimum}, {maximum}]")

    def skill_levels(value, location):
        levels = mapping(value, location)
        for skill_id, level in levels.items():
            reference(skill_id, skills, location)
            number(level, 0, 5, f"{location}.{skill_id}")
        return levels

    skills = {key[0] for key in index(dataset.skills, ("skill_id",), "skills")}
    employees = {key[0]: row for key, row in index(dataset.employees, ("employee_id",), "employees").items()}
    events = {key[0] for key in index(dataset.events, ("event_id",), "events")}
    profiles = index(dataset.role_profiles, ("role", "grade"), "role_profiles")
    roles = {key[0] for key in profiles}
    index(dataset.activity_history, ("record_id",), "activity_history")

    for profile in dataset.role_profiles:
        location = f"role_profiles[{profile.get('role')}/{profile.get('grade')}]"
        reference(profile.get("grade"), GRADES, f"{location}.grade")
        required = skill_levels(profile.get("required_skills"), f"{location}.required_skills")
        for skill_id in sequence(profile.get("critical_skills"), f"{location}.critical_skills"):
            reference(skill_id, skills, f"{location}.critical_skills")
            reference(skill_id, required, f"{location}.critical_skills (must be required)")

    for employee in dataset.employees:
        location = f"employees[{employee.get('employee_id')}]"
        role, grade = employee.get("role"), employee.get("grade")
        if not isinstance(role, str) or not isinstance(grade, str) or (role, grade) not in profiles:
            errors.append(f"{location}.role/grade: unknown role_profiles reference {(role, grade)!r}")
        skill_levels(employee.get("skills"), f"{location}.skills")
        if "manager_id" not in employee:
            errors.append(f"{location}.manager_id: expected employee ID or null")
        manager_id = employee.get("manager_id")
        if manager_id is not None:
            reference(manager_id, employees, f"{location}.manager_id")
            manager = employees.get(manager_id) if isinstance(manager_id, str) else None
            if manager and (manager.get("grade") != "Lead" or manager.get("department") != employee.get("department")
                            or manager_id == employee.get("employee_id")):
                errors.append(f"{location}.manager_id: must be another Lead in the same department")
        goal = employee.get("career_goal")
        if goal is not None:
            goal = mapping(goal, f"{location}.career_goal")
            target_role = goal.get("target_role") or role
            reference(target_role, roles, f"{location}.career_goal.target_role")
            target_grade = goal.get("target_grade")
            if target_grade is not None:
                if (not isinstance(target_role, str) or not isinstance(target_grade, str)
                        or (target_role, target_grade) not in profiles):
                    errors.append(f"{location}.career_goal: unknown role_profiles reference {(target_role, target_grade)!r}")

    for event in dataset.events:
        location = f"events[{event.get('event_id')}]"
        for role in sequence(event.get("target_roles"), f"{location}.target_roles"):
            reference(role, roles, f"{location}.target_roles")
        for grade in sequence(event.get("target_grades"), f"{location}.target_grades"):
            reference(grade, GRADES, f"{location}.target_grades")
        skill_levels(event.get("prerequisites"), f"{location}.prerequisites")
        for offset, gain in enumerate(sequence(event.get("develops_skills"), f"{location}.develops_skills")):
            gain_location = f"{location}.develops_skills[{offset}]"
            gain = mapping(gain, gain_location)
            reference(gain.get("skill_id"), skills, f"{gain_location}.skill_id")
            number(gain.get("gain"), 0, 5, f"{gain_location}.gain")
            number(gain.get("max_level"), 0, 5, f"{gain_location}.max_level")

    for record in dataset.activity_history:
        location = f"activity_history[{record.get('record_id')}]"
        reference(record.get("employee_id"), employees, f"{location}.employee_id")
        reference(record.get("event_id"), events, f"{location}.event_id")
        reference(record.get("status"), ("completed", "in_progress", "dropped", "no_show", "declined", "overdue"), f"{location}.status")
        reference(record.get("assigned_by"), ("self", "manager", "hr"), f"{location}.assigned_by")
        number(record.get("completion_pct"), 0, 100, f"{location}.completion_pct", integer=True)
        for field, minimum, maximum in (("score", 0, 100), ("feedback_rating", 1, 5)):
            if record.get(field) is not None:
                number(record[field], minimum, maximum, f"{location}.{field}", integer=True)
        for field in ("date", "due_date"):
            if field == "due_date" and record.get(field) is None:
                continue
            try:
                date.fromisoformat(record.get(field))
            except (TypeError, ValueError):
                errors.append(f"{location}.{field}: expected an ISO date")
    if errors:
        raise DatasetValidationError(errors)


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS skills (skill_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS role_profiles (
        role TEXT NOT NULL, grade TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (role, grade))""",
    """CREATE TABLE IF NOT EXISTS employees (
        employee_id TEXT PRIMARY KEY, role TEXT NOT NULL, grade TEXT NOT NULL,
        manager_id TEXT, payload TEXT NOT NULL,
        FOREIGN KEY (role, grade) REFERENCES role_profiles(role, grade),
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id) DEFERRABLE INITIALLY DEFERRED)""",
    "CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS activity_history (
        record_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(employee_id),
        event_id TEXT NOT NULL REFERENCES events(event_id), date TEXT NOT NULL, due_date TEXT,
        status TEXT NOT NULL, completion_pct INTEGER NOT NULL, score INTEGER,
        feedback_rating INTEGER, assigned_by TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS history_employee ON activity_history(employee_id)",
    "CREATE INDEX IF NOT EXISTS history_event ON activity_history(event_id)",
    """CREATE TABLE IF NOT EXISTS completion_requests (
        request_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(employee_id),
        event_id TEXT NOT NULL REFERENCES events(event_id), response TEXT NOT NULL)""",
)


def database_path(database_url: str | None = None) -> str:
    url = database_url if database_url is not None else os.environ.get(
        "DATABASE_URL", f"sqlite:///{ROOT / 'storage' / 'career_quest.sqlite3'}"
    )
    if not url.startswith("sqlite:///") or not url.removeprefix("sqlite:///"):
        raise ValueError("DATABASE_URL must be sqlite:///relative/path, sqlite:////absolute/path or sqlite:///:memory:")
    path = url.removeprefix("sqlite:///")
    return path if path == ":memory:" else str(Path(path).expanduser().resolve())


def load_dataset(data_dir: str | Path | None = None, database_url: str | None = None) -> dict:
    """Validate every startup; seed once in a transaction and retain existing progress."""
    dataset = read_dataset(data_dir if data_dir is not None else os.environ.get("DATA_DIR", ROOT / "data"))
    validate_dataset(dataset)
    path = database_path(database_url)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            # Explicit BEGIN covers DDL too and serializes simultaneous first starts.
            connection.execute("BEGIN IMMEDIATE")
            for statement in SCHEMA:
                connection.execute(statement)
            seeded = connection.execute("SELECT 1 FROM metadata WHERE key = 'dataset_meta'").fetchone() is None
            if seeded:
                if any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in TABLES):
                    raise ValueError("Database has data but no seed marker; refusing to overwrite it")
                for table, id_field, rows in (
                    ("skills", "skill_id", dataset.skills), ("events", "event_id", dataset.events)
                ):
                    connection.executemany(
                        f"INSERT INTO {table} ({id_field}, payload) VALUES (?, ?)",
                        [(row[id_field], json.dumps(row)) for row in rows],
                    )
                connection.executemany(
                    "INSERT INTO role_profiles (role, grade, payload) VALUES (?, ?, ?)",
                    [(row["role"], row["grade"], json.dumps(row)) for row in dataset.role_profiles],
                )
                connection.executemany(
                    "INSERT INTO employees (employee_id, role, grade, manager_id, payload) VALUES (?, ?, ?, ?, ?)",
                    [(row["employee_id"], row["role"], row["grade"], row["manager_id"], json.dumps(row)) for row in dataset.employees],
                )
                connection.executemany(
                    f"INSERT INTO activity_history ({', '.join(HISTORY_COLUMNS)}) VALUES ({', '.join('?' for _ in HISTORY_COLUMNS)})",
                    [tuple(row[column] for column in HISTORY_COLUMNS) for row in dataset.activity_history],
                )
                connection.executemany(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    [("dataset_meta", json.dumps(dataset.meta)), ("proficiency_scale", json.dumps(dataset.proficiency_scale))],
                )
            counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    return {"database": path, "seeded": seeded, "counts": counts, "reference_errors": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Dataset folder (default: DATA_DIR or repo data/)")
    parser.add_argument("--database-url", help="SQLite URL (default: DATABASE_URL or repo storage/career_quest.sqlite3)")
    args = parser.parse_args()
    try:
        result = load_dataset(args.data_dir, args.database_url)
    except (DatasetValidationError, OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
