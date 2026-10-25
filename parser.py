
import os
from pathlib import Path

from dotenv import load_dotenv
from llama_cloud import LlamaCloud


load_dotenv()


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "A concise summary of the academic document. "
                "Include its subject, purpose, and important information."
            ),
        },
        "courses": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Course names or course codes explicitly identifiable "
                "from the document. Return an empty array if none exist."
            ),
        },
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Assignment, examination, event, or task name."
                        ),
                    },
                    "due_date": {
                        "type": ["string", "null"],
                        "description": (
                            "Due date in YYYY-MM-DD format, or null "
                            "if the date is missing or ambiguous."
                        ),
                    },
                    "evidence": {
                        "type": "string",
                        "description": (
                            "Exact supporting text from the document "
                            "that establishes the task and its due date."
                        ),
                    },
                },
                "required": ["title", "due_date", "evidence"],
            },
        },
    },
    "required": ["summary", "courses", "deadlines"],
}


def parse_document(file_path: str | Path) -> dict:
    """
    Extract structured academic information from a document.

    Supported extensions:
    PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX.

    Returns:
        {
            "summary": str,
            "courses": list[str],
            "deadlines": [
                {
                    "title": str,
                    "due_date": str | None,
                    "evidence": str
                }
            ]
        }
    """

    path = Path(file_path)

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported document format.")

    if not path.is_file():
        raise FileNotFoundError("The document file does not exist.")

    api_key = os.getenv("LLAMA_API_KEY")

    if not api_key:
        raise RuntimeError("LLAMA_API_KEY is missing from the .env file.")

    client = LlamaCloud(api_key=api_key)

    uploaded_file = client.files.create(
        file=str(path),
        purpose="extract",
    )

    result = client.extract.run(
        file_input=uploaded_file.id,
        configuration={
            "data_schema": EXTRACTION_SCHEMA,
            "tier": "cost_effective",
            "version": "latest",
        },
    )

    extracted_data = result.extract_result

    if not isinstance(extracted_data, dict):
        raise RuntimeError(
            "LlamaCloud did not return structured extraction results."
        )

    required_fields = {"summary", "courses", "deadlines"}

    if not required_fields.issubset(extracted_data):
        raise RuntimeError(
            "The extracted result is missing required fields."
        )

    if not isinstance(extracted_data["summary"], str):
        raise RuntimeError("The extracted summary has an invalid format.")

    if not isinstance(extracted_data["courses"], list):
        raise RuntimeError("The extracted courses have an invalid format.")

    if not isinstance(extracted_data["deadlines"], list):
        raise RuntimeError("The extracted deadlines have an invalid format.")

    for course in extracted_data["courses"]:
        if not isinstance(course, str):
            raise RuntimeError("An extracted course has an invalid format.")

    for deadline in extracted_data["deadlines"]:
        if not isinstance(deadline, dict):
            raise RuntimeError("An extracted deadline has an invalid format.")

        if not all(
            key in deadline
            for key in ("title", "due_date", "evidence")
        ):
            raise RuntimeError(
                "An extracted deadline is missing required fields."
            )

        due_date = deadline["due_date"]

        if due_date is not None:
            if not isinstance(due_date, str):
                raise RuntimeError("An extracted due date is invalid.")

            from datetime import date

            try:
                date.fromisoformat(due_date)
            except ValueError as exc:
                raise RuntimeError(
                    "An extracted due date is not a valid ISO date."
                ) from exc

    return extracted_data
