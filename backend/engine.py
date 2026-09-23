"""Deterministic, offline recommendations over a validated loader Dataset."""

import argparse
import json
import os
from collections import defaultdict
from datetime import date

from backend.loader import Dataset, GRADES, ROOT, read_dataset, validate_dataset


CRITICAL_WEIGHT = 3.0
DECLINE_PENALTY = 0.6
SELF_COMPLETE_BONUS = 1.15
MIN_ENGAGEMENT = 0.2
MAX_ENGAGEMENT = 1.3
SKIP_STATUSES = frozenset({"declined", "no_show", "dropped"})
REPEATABLE_EVENT_ID = "EV_036"


class RecommendationEngine:
    def __init__(self, dataset: Dataset):
        self.as_of = date.fromisoformat(dataset.meta["skills"]["as_of_date"])
        self.employees = {row["employee_id"]: row for row in dataset.employees}
        self.events = {row["event_id"]: row for row in dataset.events}
        self.profiles = {(row["role"], row["grade"]): row for row in dataset.role_profiles}
        self.skill_names = {row["skill_id"]: row["name"] for row in dataset.skills}
        self.history = defaultdict(list)
        ratings = defaultdict(list)
        for row in dataset.activity_history:
            if date.fromisoformat(row["date"]) <= self.as_of:
                self.history[row["employee_id"]].append(row)
                if row["feedback_rating"] is not None:
                    ratings[row["event_id"]].append(row["feedback_rating"])
        for rows in self.history.values():
            rows.sort(key=lambda row: (row["date"], row["record_id"]))
        self.average_ratings = {
            event_id: sum(values) / len(values) for event_id, values in ratings.items()
        }

    def _target_profile(self, employee: dict) -> dict:
        goal = employee.get("career_goal") or {}
        target_role = goal.get("target_role") or employee["role"]
        target_grade = goal.get("target_grade")
        if not target_grade:
            grade_index = GRADES.index(employee["grade"])
            target_grade = GRADES[min(grade_index + 1, len(GRADES) - 1)]
        return self.profiles[target_role, target_grade]

    def _engagement_by_type(self, history: list[dict]) -> dict:
        by_type = {
            event_type: {"skip_count": 0, "self_completion_count": 0, "records": []}
            for event_type in sorted({event["type"] for event in self.events.values()})
        }
        for record in history:
            event_type = self.events[record["event_id"]]["type"]
            summary = by_type[event_type]
            if record["status"] in SKIP_STATUSES:
                summary["skip_count"] += 1
                weight = DECLINE_PENALTY
            elif record["status"] == "completed" and record["assigned_by"] == "self":
                summary["self_completion_count"] += 1
                weight = SELF_COMPLETE_BONUS
            else:
                continue
            summary["records"].append({
                key: record[key] for key in ("record_id", "event_id", "date", "status", "assigned_by")
            } | {"weight": weight})
        for summary in by_type.values():
            raw = DECLINE_PENALTY ** summary["skip_count"] * SELF_COMPLETE_BONUS ** summary["self_completion_count"]
            summary["raw_multiplier"] = raw
            summary["multiplier"] = max(MIN_ENGAGEMENT, min(raw, MAX_ENGAGEMENT))
        return by_type

    def _availability(self, event: dict) -> str | None:
        if event["format"] == "self_paced":
            return self.as_of.isoformat()
        upcoming = [
            date.fromisoformat(value) for value in event["upcoming_sessions"]
            if date.fromisoformat(value) >= self.as_of
        ]
        return min(upcoming).isoformat() if upcoming else None

    @staticmethod
    def _eligibility(employee: dict, current: dict, event: dict, completed: set) -> list[str]:
        failures = []
        if any(current.get(skill_id, 0) < required for skill_id, required in event["prerequisites"].items()):
            failures.append("unmet_prerequisites")
        if employee["role"] not in event["target_roles"]:
            failures.append("wrong_role")
        if employee["grade"] not in event["target_grades"]:
            failures.append("wrong_grade")
        if event["mandatory"]:
            failures.append("mandatory")
        if event["event_id"] in completed and event["event_id"] != REPEATABLE_EVENT_ID:
            failures.append("already_completed")
        return failures

    def evaluate(self, employee_id: str) -> list[dict]:
        """Score every event; failed hard filters always receive zero and reasons."""
        employee = self.employees[employee_id]
        history = self.history.get(employee_id, [])
        profile = self._target_profile(employee)
        current = employee["skills"]
        engagement_by_type = self._engagement_by_type(history)
        completed = {row["event_id"] for row in history if row["status"] == "completed"}
        required = profile["required_skills"]
        critical = set(profile["critical_skills"])
        results = []
        for event_id, event in sorted(self.events.items()):
            failures = self._eligibility(employee, current, event, completed)
            gaps_used = []
            if not failures:
                for gain in event["develops_skills"]:
                    skill_id = gain["skill_id"]
                    level = current.get(skill_id, 0)
                    gap = max(0, required.get(skill_id, 0) - level)
                    if gap <= 0:
                        continue
                    effective_gain = max(0, min(gain["gain"], gain["max_level"] - level, gap))
                    weight = CRITICAL_WEIGHT if skill_id in critical else 1.0
                    gaps_used.append({
                        "skill_id": skill_id, "skill_name": self.skill_names[skill_id],
                        "current": level, "required": required[skill_id], "gap": gap,
                        "critical": skill_id in critical, "weight": weight,
                        "gain": gain["gain"], "max_level": gain["max_level"],
                        "effective_gain": effective_gain, "contribution": effective_gain * weight,
                    })
            benefit = sum(item["contribution"] for item in gaps_used)
            engagement = engagement_by_type[event["type"]]["multiplier"]
            score = benefit * engagement if not failures else 0.0
            results.append({
                "event_id": event_id, "title": event["title"], "type": event["type"],
                "score": score, "eligible": not failures, "exclusion_reasons": failures,
                "factors": {
                    "as_of_date": self.as_of.isoformat(),
                    "current_role": employee["role"], "current_grade": employee["grade"],
                    "target_role": profile["role"], "target_grade": profile["grade"],
                    "gaps_used": gaps_used, "benefit": benefit,
                    "skill_basis": "assessed_employee_skills",
                    "engagement_type": event["type"], "engagement_multiplier": engagement,
                    # Other types explain alternatives; only this event's type multiplies its benefit.
                    "engagement_by_type": engagement_by_type,
                    "tie_break": {
                        "available_on": self._availability(event),
                        "duration_hours": event["duration_hours"],
                        "avg_feedback_rating": self.average_ratings.get(event_id),
                    },
                },
            })
        return results

    def recommend(self, employee_id: str, limit: int = 3) -> list[dict]:
        """Return at most 1-3 positive, eligible candidates in deterministic order."""
        if type(limit) is not int or not 1 <= limit <= 3:
            raise ValueError("limit must be an integer from 1 to 3")
        candidates = [row for row in self.evaluate(employee_id) if row["eligible"] and row["score"] > 0]

        def order(row):
            tie = row["factors"]["tie_break"]
            return (
                -row["score"], tie["available_on"] or date.max.isoformat(),
                tie["duration_hours"], -(tie["avg_feedback_rating"] or 0), row["event_id"],
            )

        return sorted(candidates, key=order)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("employee_id")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", ROOT / "data"))
    parser.add_argument("--limit", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    try:
        dataset = read_dataset(args.data_dir)
        validate_dataset(dataset)
        recommendations = RecommendationEngine(dataset).recommend(args.employee_id, args.limit)
    except (KeyError, ValueError) as exc:
        parser.exit(1, f"Cannot recommend for {args.employee_id}: {exc}\n")
    print(json.dumps({"employee_id": args.employee_id, "recommendations": recommendations}, indent=2))


if __name__ == "__main__":
    main()
