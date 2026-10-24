
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    course_code: str
    course_name: str
    instructor: str | None = None

    @field_validator("course_code")
    @classmethod
    def normalize_course_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Course code cannot be empty")
        return value

    @field_validator("course_name")
    @classmethod
    def validate_course_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Course name cannot be empty")
        return value


class DocumentCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    filename: str
    object_key: str
    content_type: str
    size: int = Field(gt=0)
    course_ids: list[str] = Field(default_factory=list)
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class DeadlineCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str
    description: str = ""
    due_at: datetime
    course_id: str | None = None
    status: Literal["not_started", "in_progress", "completed"] = "not_started"

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Deadline title cannot be empty")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("due_at", mode="before")
    @classmethod
    def validate_due_at(cls, value: datetime) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Due date must include a timezone")

        return value.astimezone(timezone.utc)
