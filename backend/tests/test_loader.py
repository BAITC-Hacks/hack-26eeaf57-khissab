import copy
import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.loader import (
    GRADES,
    HISTORY_COLUMNS,
    ROOT,
    SCHEMA,
    TABLES,
    DatasetValidationError,
    database_path,
    load_dataset,
    read_dataset,
    validate_dataset,
)


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "data"
        self.directory.mkdir()
        self.db_file = Path(self.temp.name) / "storage" / "test.sqlite3"
        self.db_url = f"sqlite:///{self.db_file}"
        meta = {"dataset": "Synthetic test", "as_of_date": "2026-10-01"}
        employee = {
            "employee_id": "TEST_EMPLOYEE", "full_name": "Test Employee", "department": "Test",
            "role": "Test Role", "grade": "Junior", "manager_id": "TEST_LEAD",
            "hire_date": "2025-01-01", "tenure_months": 21, "work_format": "remote",
            "preferred_language": "en", "career_goal": {"target_role": "Test Role", "target_grade": "Middle"},
            "skills": {"TEST_SKILL": 1}, "last_review_date": "2026-09-01",
        }
        lead = {**employee, "employee_id": "TEST_LEAD", "grade": "Lead", "manager_id": None, "career_goal": None}
        self.documents = {
            "skills": {
                "meta": meta, "proficiency_scale": {str(level): str(level) for level in range(6)},
                "skills": [{"skill_id": "TEST_SKILL", "name": "Test Skill", "type": "hard", "category": "test", "description": "Test"}],
                "role_profiles": [
                    {"role": "Test Role", "grade": grade, "required_skills": {"TEST_SKILL": index + 1}, "critical_skills": ["TEST_SKILL"]}
                    for index, grade in enumerate(GRADES)
                ],
            },
            "employees": {"meta": meta, "employees": [employee, lead]},
            "events": {
                "meta": meta,
                "events": [{
                    "event_id": "TEST_EVENT", "title": "Test Course", "description": "Test",
                    "type": "course", "format": "self_paced", "duration_hours": 2, "mandatory": False,
                    "target_roles": ["Test Role"], "target_grades": list(GRADES),
                    "develops_skills": [{"skill_id": "TEST_SKILL", "gain": 1, "max_level": 4}],
                    "prerequisites": {"TEST_SKILL": 1}, "upcoming_sessions": [],
                }],
            },
        }
        self.history = [{
            "record_id": "TEST_RECORD", "employee_id": "TEST_EMPLOYEE", "event_id": "TEST_EVENT",
            "date": "2026-09-15", "due_date": "", "status": "completed", "completion_pct": "100",
            "score": "", "feedback_rating": "4", "assigned_by": "self",
        }]
        self.write_sources()

    def write_sources(self):
        for name, document in self.documents.items():
            (self.directory / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
        with (self.directory / "activity_history.csv").open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=HISTORY_COLUMNS)
            writer.writeheader()
            writer.writerows(self.history)

    def test_round_trip_preserves_profiles_history_and_metadata(self):
        self.assertFalse(self.db_file.parent.exists())
        result = load_dataset(self.directory, self.db_url)
        self.assertEqual(result["counts"], {"employees": 2, "events": 1, "skills": 1, "activity_history": 1, "role_profiles": 4})
        self.assertTrue(result["seeded"])
        self.assertEqual(result["reference_errors"], 0)
        dataset = read_dataset(self.directory)
        with closing(sqlite3.connect(self.db_file)) as connection:
            for table in ("skills", "role_profiles", "employees", "events"):
                stored = [json.loads(row[0]) for row in connection.execute(f"SELECT payload FROM {table} ORDER BY payload")]
                expected = getattr(dataset, table)
                self.assertCountEqual(stored, expected)
            metadata = {key: json.loads(value) for key, value in connection.execute("SELECT key, value FROM metadata")}
            self.assertEqual(metadata["dataset_meta"], dataset.meta)
            self.assertEqual(metadata["proficiency_scale"], dataset.proficiency_scale)
            record = connection.execute(f"SELECT {', '.join(HISTORY_COLUMNS)} FROM activity_history").fetchone()
            self.assertEqual(dict(zip(HISTORY_COLUMNS, record)), dataset.activity_history[0])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(dataset.activity_history[0]["completion_pct"], 100)
        self.assertEqual(dataset.activity_history[0]["feedback_rating"], 4)
        self.assertIsNone(dataset.activity_history[0]["score"])
        self.assertIsNone(dataset.activity_history[0]["due_date"])

    def test_all_cross_references_reject_unknown_ids(self):
        original = read_dataset(self.directory)
        cases = [
            ("employees", (0, "skills"), {"MISSING": 2}, "employees[TEST_EMPLOYEE].skills"),
            ("employees", (0, "manager_id"), "MISSING", ".manager_id"),
            ("employees", (0, "role"), "MISSING", ".role/grade"),
            ("employees", (0, "grade"), "MISSING", ".role/grade"),
            ("employees", (0, "career_goal", "target_role"), "MISSING", ".career_goal"),
            ("employees", (0, "career_goal", "target_grade"), "MISSING", ".career_goal"),
            ("role_profiles", (0, "required_skills"), {"MISSING": 2}, ".required_skills"),
            ("role_profiles", (0, "critical_skills"), ["MISSING"], ".critical_skills"),
            ("events", (0, "develops_skills", 0, "skill_id"), "MISSING", ".develops_skills[0].skill_id"),
            ("events", (0, "prerequisites"), {"MISSING": 2}, ".prerequisites"),
            ("events", (0, "target_roles"), ["MISSING"], ".target_roles"),
            ("events", (0, "target_grades"), ["MISSING"], ".target_grades"),
            ("activity_history", (0, "employee_id"), "MISSING", "activity_history[TEST_RECORD].employee_id"),
            ("activity_history", (0, "event_id"), "MISSING", "activity_history[TEST_RECORD].event_id"),
        ]
        for collection, path, value, diagnostic in cases:
            with self.subTest(collection=collection, path=path):
                dataset = copy.deepcopy(original)
                target = getattr(dataset, collection)
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(DatasetValidationError) as caught:
                    validate_dataset(dataset)
                self.assertIn(diagnostic, str(caught.exception))
                self.assertIn("MISSING", str(caught.exception))

    def test_errors_are_aggregated_before_creating_database(self):
        self.documents["employees"]["employees"][0]["manager_id"] = "BAD_MANAGER"
        self.history[0]["event_id"] = "BAD_EVENT"
        self.write_sources()
        with self.assertRaises(DatasetValidationError) as caught:
            load_dataset(self.directory, self.db_url)
        self.assertEqual(len(caught.exception.errors), 2)
        self.assertIn("BAD_MANAGER", str(caught.exception))
        self.assertIn("BAD_EVENT", str(caught.exception))
        self.assertFalse(self.db_file.parent.exists())

    def test_duplicate_ids_are_rejected_for_every_collection(self):
        for collection in TABLES:
            with self.subTest(collection=collection):
                dataset = read_dataset(self.directory)
                rows = getattr(dataset, collection)
                rows.append(copy.deepcopy(rows[0]))
                with self.assertRaisesRegex(DatasetValidationError, "duplicate ID"):
                    validate_dataset(dataset)

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        path = self.directory / "employees.json"
        path.write_text('{"meta": {}, "employees": [], "employees": []}', encoding="utf-8")
        with self.assertRaisesRegex(DatasetValidationError, "duplicate JSON key 'employees'"):
            load_dataset(self.directory, self.db_url)

    def test_restart_preserves_changed_skills_and_history(self):
        load_dataset(self.directory, self.db_url)
        with closing(sqlite3.connect(self.db_file)) as connection, connection:
            employee = copy.deepcopy(self.documents["employees"]["employees"][0])
            employee["skills"]["TEST_SKILL"] = 5
            connection.execute("UPDATE employees SET payload = ? WHERE employee_id = ?", (json.dumps(employee), employee["employee_id"]))
            connection.execute("UPDATE activity_history SET feedback_rating = 5")
        result = load_dataset(self.directory, self.db_url)
        self.assertFalse(result["seeded"])
        self.assertEqual(result["counts"]["activity_history"], 1)
        with closing(sqlite3.connect(self.db_file)) as connection:
            stored = json.loads(connection.execute("SELECT payload FROM employees WHERE employee_id = 'TEST_EMPLOYEE'").fetchone()[0])
            self.assertEqual(stored["skills"]["TEST_SKILL"], 5)
            self.assertEqual(connection.execute("SELECT feedback_rating FROM activity_history").fetchone()[0], 5)

    def test_invalid_source_does_not_change_existing_database(self):
        load_dataset(self.directory, self.db_url)
        before = self.db_file.read_bytes()
        self.history[0]["employee_id"] = "MISSING"
        self.write_sources()
        with self.assertRaises(DatasetValidationError):
            load_dataset(self.directory, self.db_url)
        self.assertEqual(self.db_file.read_bytes(), before)

    def test_sql_failure_rolls_back_entire_seed(self):
        self.db_file.parent.mkdir()
        with closing(sqlite3.connect(self.db_file)) as connection, connection:
            for statement in SCHEMA:
                connection.execute(statement)
            connection.execute("""CREATE TRIGGER fail_history BEFORE INSERT ON activity_history
                BEGIN SELECT RAISE(ABORT, 'test import failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test import failure"):
            load_dataset(self.directory, self.db_url)
        with closing(sqlite3.connect(self.db_file)) as connection:
            for table in (*TABLES, "metadata"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_extended_profiles_and_history_are_not_limited_to_seed_counts(self):
        extra = copy.deepcopy(self.documents["employees"]["employees"][0])
        extra["employee_id"] = "TEST_ADDED"
        extra["skills"] = {}
        extra["career_goal"] = None
        self.documents["employees"]["employees"].append(extra)
        self.history.append({**self.history[0], "record_id": "TEST_ADDED_RECORD", "employee_id": extra["employee_id"]})
        self.write_sources()
        result = load_dataset(self.directory, "sqlite:///:memory:")
        self.assertEqual(result["counts"]["employees"], 3)
        self.assertEqual(result["counts"]["activity_history"], 2)

    def test_invalid_csv_values_and_dates_are_rejected(self):
        for field, value in (("score", "bad"), ("completion_pct", ""), ("completion_pct", "101"), ("feedback_rating", "0"), ("date", "2026-02-30")):
            with self.subTest(field=field, value=value):
                original = self.history[0][field]
                self.history[0][field] = value
                self.write_sources()
                with self.assertRaisesRegex(DatasetValidationError, field):
                    load_dataset(self.directory, self.db_url)
                self.history[0][field] = original

    def test_missing_csv_column_is_rejected(self):
        (self.directory / "activity_history.csv").write_text("record_id,employee_id\nTEST_RECORD,TEST_EMPLOYEE\n", encoding="utf-8")
        with self.assertRaisesRegex(DatasetValidationError, "expected columns"):
            read_dataset(self.directory)

    def test_wrong_row_shape_is_rejected(self):
        self.documents["events"]["events"] = {"event_id": "TEST_EVENT"}
        self.write_sources()
        with self.assertRaisesRegex(DatasetValidationError, "events.json.events"):
            read_dataset(self.directory)

    def test_default_and_environment_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(database_path(), str(ROOT / "storage" / "career_quest.sqlite3"))
        with patch.dict(os.environ, {"DATA_DIR": str(self.directory), "DATABASE_URL": self.db_url}):
            self.assertEqual(database_path(), str(self.db_file.resolve()))
            self.assertEqual(load_dataset()["counts"]["employees"], 2)
        self.assertEqual(database_path("sqlite:////app/storage/career_quest.sqlite3"), "/app/storage/career_quest.sqlite3")
        self.assertEqual(database_path("sqlite:///./storage/career_quest.sqlite3"), str(Path("storage/career_quest.sqlite3").resolve()))
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            database_path("postgresql://localhost/career_quest")

    def test_cli_error_has_nonzero_exit_and_record_location(self):
        self.history[0]["event_id"] = "MISSING"
        self.write_sources()
        result = subprocess.run(
            [sys.executable, "-m", "backend.loader", "--data-dir", str(self.directory), "--database-url", self.db_url],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("activity_history[TEST_RECORD].event_id: unknown reference 'MISSING'", result.stderr)
        self.assertFalse(self.db_file.exists())


class StarterKitSmokeTest(unittest.TestCase):
    @unittest.skipUnless((ROOT / "data" / "employees.json").is_file(), "Starter kit is not installed in data/")
    def test_starter_kit_counts_and_all_references(self):
        result = load_dataset(ROOT / "data", "sqlite:///:memory:")
        self.assertEqual(result["counts"], {"employees": 200, "events": 40, "skills": 60, "activity_history": 2743, "role_profiles": 32})
        self.assertEqual(result["reference_errors"], 0)


if __name__ == "__main__":
    unittest.main()
