"""Deterministic, offline recommendations over a validated loader Dataset."""

import argparse
import copy
import json
import math
import os
from collections import defaultdict
from datetime import date

from backend.loader import Dataset, GRADES, ROOT, read_dataset, validate_dataset


CRITICAL_WEIGHT = 3.0
DECLINE_PENALTY = 0.6
SELF_COMPLETE_BONUS = 1.15
MAX_SELF_FACTOR = 1.3
MAX_BONUS_COMPLETIONS = math.ceil(math.log(MAX_SELF_FACTOR, SELF_COMPLETE_BONUS))
MIN_ENGAGEMENT = 0.2
MAX_ENGAGEMENT = 1.3
SKIP_STATUSES = frozenset({"declined", "no_show", "dropped"})
REPEATABLE_EVENT_ID = "EV_036"


class RecommendationEngine:
    def __init__(self, dataset: Dataset):
        self.as_of = date.fromisoformat(dataset.meta["skills"]["as_of_date"])
        self.employees = {row["employee_id"]: copy.deepcopy(row) for row in dataset.employees}
        self.assessed_skills = {row["employee_id"]: dict(row["skills"]) for row in dataset.employees}
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
        live_order = {record_id: index for index, record_id in enumerate(dataset.completion_record_ids)}
        self.skill_updates = defaultdict(list)
        for employee_id, rows in self.history.items():
            rows.sort(key=lambda row: (row["date"], live_order.get(row["record_id"], -1), row["event_id"], row["record_id"]))
            employee = self.employees.get(employee_id)
            if employee is None:
                continue
            for row in rows:
                if row["status"] != "completed" or (
                    row["date"] <= employee["last_review_date"] and row["record_id"] not in live_order
                ):
                    continue
                for gain in self.events[row["event_id"]]["develops_skills"]:
                    skill_id = gain["skill_id"]
                    before = employee["skills"].get(skill_id, 0)
                    after = before + max(0, min(gain["gain"], gain["max_level"] - before))
                    employee["skills"][skill_id] = after
                    if after > before:
                        self.skill_updates[employee_id].append({
                            "record_id": row["record_id"], "event_id": row["event_id"], "date": row["date"],
                            "skill_id": skill_id, "before": before, "after": after, "gain": after - before,
                        })
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
            summary["decline_factor"] = DECLINE_PENALTY ** summary["skip_count"]
            # Capping the exponent also prevents overflow with large uploaded histories.
            summary["self_factor"] = min(
                SELF_COMPLETE_BONUS ** min(summary["self_completion_count"], MAX_BONUS_COMPLETIONS),
                MAX_SELF_FACTOR,
            )
            raw = summary["decline_factor"] * summary["self_factor"]
            summary["raw_multiplier"] = raw
            summary["multiplier"] = max(MIN_ENGAGEMENT, min(raw, MAX_ENGAGEMENT))
        return by_type

    def trajectory(self, employee_id: str) -> dict:
        employee = self.employees[employee_id]
        profile = self._target_profile(employee)
        skills = [{
            "skill_id": skill_id, "skill_name": self.skill_names[skill_id],
            "current": employee["skills"].get(skill_id, 0), "required": required,
            "gap": max(0, required - employee["skills"].get(skill_id, 0)),
            "critical": skill_id in profile["critical_skills"],
        } for skill_id, required in sorted(profile["required_skills"].items())]
        required_total = sum(row["required"] for row in skills)
        total_gap = sum(row["gap"] for row in skills)
        return {
            "target_role": profile["role"], "target_grade": profile["grade"], "skills": skills,
            "total_gap": total_gap,
            "critical_gap": sum(row["gap"] for row in skills if row["critical"]),
            "progress_pct": round(100 * (1 - total_gap / required_total), 2) if required_total else 100.0,
        }

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

    def _add_gateways(self, results: list[dict], current: dict) -> None:
        eligible_by_skill = defaultdict(list)
        for result in results:
            for gap in result["factors"]["gaps_used"]:
                if gap["critical"] and gap["effective_gain"] > 0:
                    eligible_by_skill[gap["skill_id"]].append(result["event_id"])
        for result in results:
            gateways = []
            result["factors"]["gateway_to"] = gateways
            if not result["eligible"] or result["score"] <= 0:
                continue
            unique_gaps = {
                gap["skill_id"]: gap for gap in result["factors"]["gaps_used"]
                if gap["critical"] and eligible_by_skill[gap["skill_id"]] == [result["event_id"]]
            }
            if not unique_gaps:
                continue
            projected = dict(current)
            for gain in self.events[result["event_id"]]["develops_skills"]:
                level = projected.get(gain["skill_id"], 0)
                projected[gain["skill_id"]] = level + max(0, min(gain["gain"], gain["max_level"] - level))
            for locked in results:
                # A gateway cannot bypass role, grade, mandatory, or completion restrictions.
                if locked["exclusion_reasons"] != ["unmet_prerequisites"]:
                    continue
                event = self.events[locked["event_id"]]
                better_skills = [
                    {"skill_id": gain["skill_id"], "skill_name": unique_gaps[gain["skill_id"]]["skill_name"],
                     "current_max_level": unique_gaps[gain["skill_id"]]["max_level"],
                     "next_max_level": gain["max_level"], "required": unique_gaps[gain["skill_id"]]["required"]}
                    for gain in event["develops_skills"]
                    if gain["skill_id"] in unique_gaps and gain["gain"] > 0
                    and min(gain["max_level"], unique_gaps[gain["skill_id"]]["required"])
                    > min(unique_gaps[gain["skill_id"]]["max_level"], unique_gaps[gain["skill_id"]]["required"])
                ]
                if not better_skills:
                    continue
                blockers = [{
                    "skill_id": skill_id, "skill_name": self.skill_names[skill_id],
                    "current": current.get(skill_id, 0), "required": required,
                    "after_completion": projected.get(skill_id, 0),
                    "met_after_completion": projected.get(skill_id, 0) >= required,
                } for skill_id, required in sorted(event["prerequisites"].items()) if current.get(skill_id, 0) < required]
                if not any(blocker["after_completion"] > blocker["current"] for blocker in blockers):
                    continue
                gateways.append({
                    "event_id": event["event_id"], "title": event["title"],
                    "critical_skills": better_skills, "blocking_prerequisites": blockers,
                    "unlocked_after_completion": all(blocker["met_after_completion"] for blocker in blockers),
                })

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
                    "skill_basis": "assessment_plus_completed_history",
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
        self._add_gateways(results, current)
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
