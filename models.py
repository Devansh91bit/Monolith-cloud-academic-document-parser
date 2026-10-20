from datetime import datetime, timezone

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