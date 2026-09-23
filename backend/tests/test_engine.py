import copy
import unittest

from backend.engine import RecommendationEngine
from backend.loader import Dataset, GRADES, ROOT, read_dataset, validate_dataset


SYSTEM = "SK_SYSTEM_DESIGN"
SPEAKING = "SK_PUBLIC_SPEAKING"
SQL = "SK_SQL"
OBSERVABILITY = "SK_OBSERVABILITY"


def event(event_id, skill=SYSTEM, gain=1, **overrides):
    return {
        "event_id": event_id, "title": event_id, "description": "Synthetic test event",
        "type": "course", "format": "self_paced", "duration_hours": 2, "mandatory": False,
        "target_roles": ["Backend Engineer"], "target_grades": list(GRADES),
        "develops_skills": [{"skill_id": skill, "gain": gain, "max_level": 5}],
        "prerequisites": {}, "upcoming_sessions": [], **overrides,
    }


def record(record_id, event_id, status="completed", assigned_by="self", **overrides):
    return {
        "record_id": record_id, "employee_id": "TEST_EMPLOYEE", "event_id": event_id,
        "date": "2026-09-20", "due_date": None, "status": status,
        "completion_pct": 100 if status == "completed" else 0,
        "score": None, "feedback_rating": None, "assigned_by": assigned_by, **overrides,
    }


def dataset(events=None, history=None):
    return Dataset(
        meta={"skills": {"as_of_date": "2026-10-01"}},
        proficiency_scale={str(level): str(level) for level in range(6)},
        skills=[{"skill_id": skill, "name": skill} for skill in (SYSTEM, SPEAKING, SQL, OBSERVABILITY)],
        role_profiles=[{
            "role": "Backend Engineer", "grade": grade,
            "required_skills": {SYSTEM: 4, SPEAKING: 5, SQL: 4, OBSERVABILITY: 4},
            "critical_skills": [SYSTEM],
        } for grade in GRADES],
        employees=[{
            "employee_id": "TEST_EMPLOYEE", "full_name": "Synthetic Employee", "department": "Engineering",
            "role": "Backend Engineer", "grade": "Middle", "manager_id": None,
            "hire_date": "2024-01-01", "tenure_months": 33, "work_format": "remote",
            "preferred_language": "en", "last_review_date": "2026-09-01",
            "career_goal": {"target_role": "Backend Engineer", "target_grade": "Senior"},
            "skills": {SYSTEM: 2, SPEAKING: 0, SQL: 2, OBSERVABILITY: 2},
        }],
        events=events if events is not None else [event("CRITICAL")],
        activity_history=history or [],
    )


def adversarial_dataset():
    events = [
        event("LOWEST_SKILL", SPEAKING, gain=5, type="workshop"),
        event("CRITICAL"),
        event("SQL", SQL, gain=2, type="certification"),
        event("OBSERVABILITY", OBSERVABILITY, gain=2, type="mentoring"),
    ]
    history = []
    for index, status in enumerate(("declined", "no_show", "dropped")):
        event_id = f"PAST_WORKSHOP_{index}"
        events.append(event(event_id, type="workshop", format="online", develops_skills=[]))
        history.append(record(
            f"SKIP_{index}", event_id, status, "manager",
            completion_pct=50 if status == "dropped" else 0,
        ))
    return dataset(events, history)


class EngineTests(unittest.TestCase):
    def test_adversarial_trap_requires_both_type_history_and_critical_weight(self):
        data = adversarial_dataset()
        validate_dataset(data)
        employee = data.employees[0]
        self.assertEqual([skill for skill, level in employee["skills"].items() if level == 0], [SPEAKING])
        engine = RecommendationEngine(data)
        evaluated = {row["event_id"]: row for row in engine.evaluate("TEST_EMPLOYEE")}
        self.assertTrue(evaluated["LOWEST_SKILL"]["eligible"])
        self.assertAlmostEqual(evaluated["LOWEST_SKILL"]["score"], 5 * 0.6 ** 3)
        self.assertEqual(evaluated["CRITICAL"]["score"], 3)
        recommendations = engine.recommend("TEST_EMPLOYEE")
        ids = [row["event_id"] for row in recommendations]
        self.assertEqual(len(ids), 3)
        self.assertNotIn("LOWEST_SKILL", ids)
        self.assertIn("CRITICAL", ids)
        factors = recommendations[0]["factors"]
        self.assertEqual(factors["target_grade"], "Senior")
        gap = factors["gaps_used"][0]
        self.assertEqual((gap["skill_id"], gap["current"], gap["required"], gap["gap"]), (SYSTEM, 2, 4, 2))
        self.assertTrue(gap["critical"])
        skipped = factors["engagement_by_type"]["workshop"]
        self.assertEqual(skipped["skip_count"], 3)
        self.assertEqual({r["status"] for r in skipped["records"]}, {"declined", "no_show", "dropped"})
        self.assertNotIn("LOWEST_SKILL", {r["event_id"] for r in skipped["records"]})
        self.assertAlmostEqual(skipped["multiplier"], 0.216)
        self.assertEqual(factors["engagement_multiplier"], 1)

        no_history = copy.deepcopy(data)
        no_history.activity_history = []
        self.assertEqual(RecommendationEngine(no_history).recommend("TEST_EMPLOYEE")[0]["event_id"], "LOWEST_SKILL")
        no_critical_weight = copy.deepcopy(data)
        for profile in no_critical_weight.role_profiles:
            profile["critical_skills"] = []
        unweighted = RecommendationEngine(no_critical_weight).recommend("TEST_EMPLOYEE")
        self.assertNotIn("CRITICAL", [row["event_id"] for row in unweighted])

    def test_each_hard_filter_excludes_even_high_benefit_events(self):
        cases = [
            ({"prerequisites": {SYSTEM: 3, SQL: 1}}, [], "unmet_prerequisites"),
            ({"prerequisites": {"MISSING_EMPLOYEE_SKILL": 1}}, [], "unmet_prerequisites"),
            ({"target_roles": ["Data Analyst"]}, [], "wrong_role"),
            ({"target_grades": ["Senior"]}, [], "wrong_grade"),
            ({"mandatory": True}, [], "mandatory"),
            ({}, [record("DONE", "BLOCKED")], "already_completed"),
        ]
        for overrides, history, reason in cases:
            with self.subTest(reason=reason, overrides=overrides):
                data = dataset([event("BLOCKED", gain=5, **overrides), event("ALLOWED")], history)
                engine = RecommendationEngine(data)
                self.assertEqual([r["event_id"] for r in engine.recommend("TEST_EMPLOYEE")], ["ALLOWED"])
                blocked = next(r for r in engine.evaluate("TEST_EMPLOYEE") if r["event_id"] == "BLOCKED")
                self.assertFalse(blocked["eligible"])
                self.assertEqual(blocked["score"], 0)
                self.assertIn(reason, blocked["exclusion_reasons"])

    def test_prerequisite_equality_and_current_grade_are_eligible(self):
        data = dataset([event("ALLOWED", prerequisites={SYSTEM: 2, SQL: 2}, target_grades=["Middle"])])
        self.assertEqual([r["event_id"] for r in RecommendationEngine(data).recommend("TEST_EMPLOYEE")], ["ALLOWED"])

    def test_repeatable_exception_only_bypasses_completed_id(self):
        data = dataset([event("EV_036"), event("OTHER_SAME_TYPE")], [record("DONE", "EV_036")])
        self.assertEqual(len(RecommendationEngine(data).recommend("TEST_EMPLOYEE")), 2)
        data.events[0]["mandatory"] = True
        self.assertEqual([r["event_id"] for r in RecommendationEngine(data).recommend("TEST_EMPLOYEE")], ["OTHER_SAME_TYPE"])

    def test_completion_exclusion_is_by_id_and_any_assignment(self):
        for assigned_by in ("self", "manager", "hr"):
            with self.subTest(assigned_by=assigned_by):
                data = dataset([event("DONE"), event("SAME_TYPE")], [record("R", "DONE", assigned_by=assigned_by)])
                self.assertEqual([r["event_id"] for r in RecommendationEngine(data).recommend("TEST_EMPLOYEE")], ["SAME_TYPE"])

    def test_target_goal_override_and_next_grade_including_lead_boundary(self):
        for grade, expected in (("Junior", "Middle"), ("Middle", "Senior"), ("Senior", "Lead"), ("Lead", "Lead")):
            with self.subTest(grade=grade):
                data = dataset()
                data.employees[0].update(grade=grade, career_goal=None)
                factors = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]["factors"]
                self.assertEqual(factors["target_grade"], expected)
        data = dataset()
        data.employees[0]["career_goal"]["target_grade"] = "Lead"
        data.role_profiles[-1]["required_skills"][SYSTEM] = 5
        factors = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]["factors"]
        self.assertEqual(factors["target_grade"], "Lead")
        self.assertEqual(factors["gaps_used"][0]["gap"], 3)

    def test_goal_role_selects_requirements_but_eligibility_uses_current_role(self):
        data = dataset()
        data.employees[0]["career_goal"]["target_role"] = "Architect"
        data.role_profiles.append({"role": "Architect", "grade": "Senior", "required_skills": {SYSTEM: 5}, "critical_skills": []})
        factors = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]["factors"]
        self.assertEqual(factors["target_role"], "Architect")
        self.assertEqual(factors["gaps_used"][0]["required"], 5)
        self.assertFalse(factors["gaps_used"][0]["critical"])

    def test_effective_gain_is_capped_by_gain_gap_and_max_level_with_zero_floor(self):
        for current, required, gain, cap, expected in (
            (2, 4, 1, 5, 1), (2, 4, 5, 5, 2), (2, 4, 5, 3, 1),
            (2, 4, 1, 2, 0), (3, 5, 1, 2, 0),
        ):
            with self.subTest(current=current, required=required, gain=gain, cap=cap):
                data = dataset([event("CAPPED", gain=gain)])
                data.employees[0]["skills"][SYSTEM] = current
                data.role_profiles[2]["required_skills"][SYSTEM] = required
                data.events[0]["develops_skills"][0]["max_level"] = cap
                engine = RecommendationEngine(data)
                scored = engine.evaluate("TEST_EMPLOYEE")[0]
                self.assertEqual(scored["factors"]["gaps_used"][0]["effective_gain"], expected)
                self.assertEqual(scored["score"], expected * 3)
                if expected <= 0:
                    self.assertEqual(engine.recommend("TEST_EMPLOYEE"), [])

    def test_above_cap_skill_is_zero_and_does_not_penalize_other_useful_skills(self):
        capped = {"skill_id": SYSTEM, "gain": 1, "max_level": 2}
        useful = {"skill_id": SQL, "gain": 1, "max_level": 5}
        data = dataset([
            event("CAPPED_ONLY", develops_skills=[capped]),
            event("MIXED", develops_skills=[capped, useful]),
            event("SQL_BETTER", SQL, gain=2),
        ])
        data.employees[0]["skills"][SYSTEM] = 3
        data.role_profiles[2]["required_skills"][SYSTEM] = 5
        engine = RecommendationEngine(data)
        results = engine.recommend("TEST_EMPLOYEE")
        self.assertEqual([r["event_id"] for r in results], ["SQL_BETTER", "MIXED"])
        self.assertEqual(results[1]["score"], 1)
        capped_gap, useful_gap = results[1]["factors"]["gaps_used"]
        self.assertEqual((capped_gap["current"], capped_gap["max_level"], capped_gap["required"]), (3, 2, 5))
        self.assertEqual(capped_gap["effective_gain"], 0)
        self.assertEqual(capped_gap["contribution"], 0)
        self.assertEqual(useful_gap["contribution"], 1)
        excluded = next(r for r in engine.evaluate("TEST_EMPLOYEE") if r["event_id"] == "CAPPED_ONLY")
        self.assertEqual(excluded["score"], 0)

    def test_missing_skill_defaults_to_zero_and_satisfied_skills_add_nothing(self):
        data = dataset()
        del data.employees[0]["skills"][SYSTEM]
        factors = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]["factors"]
        self.assertEqual(factors["gaps_used"][0]["current"], 0)
        self.assertEqual(factors["gaps_used"][0]["gap"], 4)
        data.employees[0]["skills"][SYSTEM] = 5
        self.assertEqual(RecommendationEngine(data).recommend("TEST_EMPLOYEE"), [])

    def test_benefit_sums_only_target_gaps_with_critical_weights(self):
        data = dataset([event("MULTI", develops_skills=[
            {"skill_id": SYSTEM, "gain": 1, "max_level": 5},
            {"skill_id": SQL, "gain": 3, "max_level": 5},
            {"skill_id": SPEAKING, "gain": 5, "max_level": 5},
        ])])
        del data.role_profiles[2]["required_skills"][SPEAKING]
        result = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]
        self.assertEqual(result["score"], 3 + 2)
        self.assertEqual([g["critical"] for g in result["factors"]["gaps_used"]], [True, False])

    def test_assessed_skills_are_not_replayed_from_post_review_completions(self):
        data = dataset(
            [event("CANDIDATE", prerequisites={SYSTEM: 3}), event("DONE", gain=3)],
            [record("AFTER_REVIEW", "DONE")],
        )
        engine = RecommendationEngine(data)
        self.assertEqual(engine.recommend("TEST_EMPLOYEE"), [])
        data.events[0]["prerequisites"] = {}
        factors = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]["factors"]
        self.assertEqual(factors["gaps_used"][0]["current"], 2)
        self.assertEqual(factors["skill_basis"], "assessed_employee_skills")

    def test_type_engagement_compounds_and_clamps_only_the_final_product(self):
        for skips, completions in ((0, 0), (1, 0), (3, 0), (4, 0), (0, 1), (0, 2), (1, 3), (4, 2)):
            with self.subTest(skips=skips, completions=completions):
                events = [event("CANDIDATE")]
                history = []
                for index in range(skips + completions):
                    event_id = f"PAST_{index}"
                    events.append(event(event_id, develops_skills=[]))
                    history.append(record(f"R{index}", event_id, "declined" if index < skips else "completed"))
                result = RecommendationEngine(dataset(events, history)).recommend("TEST_EMPLOYEE")[0]
                factors = result["factors"]
                expected = max(0.2, min(1.3, 0.6 ** skips * 1.15 ** completions))
                self.assertAlmostEqual(factors["engagement_multiplier"], expected)
                self.assertAlmostEqual(result["score"], 3 * expected)
                self.assertEqual(factors["engagement_by_type"]["course"]["self_completion_count"], completions)

    def test_only_relevant_prior_personal_history_moves_engagement(self):
        data = dataset([event("CANDIDATE"), event("PAST", develops_skills=[]), event("WORKSHOP", type="workshop")], [
            record("OTHER_PERSON", "PAST", "declined", employee_id="OTHER"),
            record("FUTURE_COMPLETION", "CANDIDATE", date="2026-10-02"),
            record("IN_PROGRESS", "PAST", "in_progress"),
            record("OVERDUE", "PAST", "overdue", "hr"),
            record("HR_DONE", "PAST", assigned_by="hr"),
            record("MANAGER_DONE", "PAST", assigned_by="manager"),
            record("OTHER_TYPE", "WORKSHOP", "dropped"),
        ])
        result = next(r for r in RecommendationEngine(data).recommend("TEST_EMPLOYEE") if r["event_id"] == "CANDIDATE")
        self.assertEqual(result["score"], 3)
        self.assertEqual(result["factors"]["engagement_by_type"]["course"]["records"], [])

    def test_availability_then_duration_then_feedback_then_id_break_ties(self):
        cases = [
            ([event("FUTURE", format="online", upcoming_sessions=["2026-11-01", "2026-09-01", "2026-10-02"], duration_hours=1),
              event("SELF_PACED", duration_hours=3),
              event("TODAY", format="online", upcoming_sessions=["2026-10-01"], duration_hours=2)], [], ["TODAY", "SELF_PACED", "FUTURE"]),
            ([event("UNKNOWN", format="online", upcoming_sessions=[]),
              event("STALE", format="online", upcoming_sessions=["2026-09-01"]),
              event("FUTURE", format="online", upcoming_sessions=["2026-11-01"])], [], ["FUTURE", "STALE", "UNKNOWN"]),
            ([event("LONG", duration_hours=5), event("SHORT", duration_hours=1)], [], ["SHORT", "LONG"]),
            ([event("A"), event("B"), event("UNRATED")], [
                record("RA", "A", employee_id="OTHER", feedback_rating=4),
                record("RB1", "B", employee_id="OTHER", feedback_rating=1),
                record("RB2", "B", employee_id="OTHER", feedback_rating=5),
                record("RB3", "B", employee_id="OTHER", feedback_rating=None),
            ], ["A", "B", "UNRATED"]),
            ([event("Z"), event("A")], [], ["A", "Z"]),
        ]
        for events, history, expected in cases:
            with self.subTest(expected=expected):
                results = RecommendationEngine(dataset(events, history)).recommend("TEST_EMPLOYEE")
                self.assertEqual([r["event_id"] for r in results], expected)

    def test_returns_one_to_three_without_padding_and_validates_limit(self):
        engine = RecommendationEngine(dataset([event(str(index)) for index in range(5)]))
        for limit in (1, 2, 3):
            self.assertEqual(len(engine.recommend("TEST_EMPLOYEE", limit)), limit)
        for invalid in (0, 4, 1.5, True):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                engine.recommend("TEST_EMPLOYEE", invalid)
        self.assertEqual(len(RecommendationEngine(dataset()).recommend("TEST_EMPLOYEE")), 1)

    def test_results_are_deterministic_and_inputs_unchanged(self):
        data = adversarial_dataset()
        before = copy.deepcopy(data)
        expected = RecommendationEngine(data).recommend("TEST_EMPLOYEE")
        self.assertEqual(data, before)
        data.events.reverse()
        data.activity_history.reverse()
        self.assertEqual(RecommendationEngine(data).recommend("TEST_EMPLOYEE"), expected)


class RealDatasetEngineTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "data" / "employees.json").is_file(), "Starter kit is not installed in data/")
    def test_all_employees_have_only_eligible_positive_recommendations(self):
        data = read_dataset(ROOT / "data")
        validate_dataset(data)
        before = copy.deepcopy(data)
        engine = RecommendationEngine(data)
        for employee in data.employees:
            with self.subTest(employee=employee["employee_id"]):
                results = engine.recommend(employee["employee_id"])
                self.assertLessEqual(len(results), 3)
                for result in results:
                    self.assertTrue(result["eligible"])
                    self.assertEqual(result["exclusion_reasons"], [])
                    self.assertGreater(result["score"], 0)
                    factors = result["factors"]
                    self.assertAlmostEqual(result["score"], factors["benefit"] * factors["engagement_multiplier"])
                    self.assertTrue(factors["gaps_used"])
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
