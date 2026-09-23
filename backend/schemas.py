"""Dataset-shaped upload and completion contracts."""

from datetime import date as Date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Text = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
Grade = Literal["Junior", "Middle", "Senior", "Lead"]
Level = Annotated[float, Field(strict=True, ge=0, le=5)]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CareerGoal(Contract):
    target_role: Text | None = None
    target_grade: Grade | None = None


class Employee(Contract):
    employee_id: Text
    full_name: Text
    department: Text
    role: Text
    grade: Grade
    manager_id: Text | None
    hire_date: Date
    tenure_months: Annotated[int, Field(strict=True, ge=0)]
    work_format: Literal["office", "hybrid", "remote"]
    preferred_language: Literal["kk", "ru", "en"]
    career_goal: CareerGoal | None
    skills: dict[Text, Level]
    last_review_date: Date


class HistoryRecord(Contract):
    record_id: Text
    employee_id: Text
    event_id: Text
    date: Date
    due_date: Date | None
    status: Literal["completed", "in_progress", "dropped", "no_show", "declined", "overdue"]
    completion_pct: Percent
    score: Percent | None
    feedback_rating: Annotated[int, Field(strict=True, ge=1, le=5)] | None
    assigned_by: Literal["self", "manager", "hr"]

    @model_validator(mode="after")
    def status_matches_progress(self):
        bounds = {
            "completed": (100, 100), "in_progress": (0, 95), "dropped": (5, 95),
            "no_show": (0, 0), "declined": (0, 0), "overdue": (0, 95),
        }
        lower, upper = bounds[self.status]
        if not lower <= self.completion_pct <= upper:
            raise ValueError(f"{self.status} requires completion_pct in [{lower}, {upper}]")
        return self


class UploadBatch(Contract):
    meta: dict | None = None
    employees: list[Employee] = Field(default_factory=list, max_length=1000)
    activity_history: list[HistoryRecord] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.employees and not self.activity_history:
            raise ValueError("Supply at least one employee or history record")
        return self


class Completion(Contract):
    employee_id: Text
    event_id: Text
    request_id: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
