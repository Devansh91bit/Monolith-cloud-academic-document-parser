
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from tempfile import SpooledTemporaryFile

from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from bson import ObjectId
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from database import create_mongodb_client, DATABASE_NAME
from models import CourseCreate, DeadlineCreate
from storage import upload_file, download_file, delete_file
from parser import parse_document


load_dotenv()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_STORAGE_SIZE = 500 * 1024 * 1024  # 500 MB

ALLOWED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = create_mongodb_client()

    try:
        app.state.mongodb_client = client
        app.state.db = client[DATABASE_NAME]
        app.state.courses_collection = app.state.db["courses"]
        app.state.documents_collection = app.state.db["documents"]
        app.state.deadlines_collection = app.state.db["deadlines"]
        app.state.storage_usage_collection = app.state.db["storage_usage"]
        app.state.parsed_documents_collection = app.state.db["parsed_documents"]

        await client.admin.command("ping")

        await app.state.courses_collection.create_index(
            [("user_id", 1), ("course_code", 1)],
            unique=True,
            name="unique_user_course_code",
        )

        await app.state.storage_usage_collection.create_index(
            [("user_id", 1)],
            unique=True,
            name="unique_user_storage_usage",
        )

        await app.state.parsed_documents_collection.create_index(
            [("user_id", 1), ("document_id", 1)],
            unique=True,
            name="unique_user_parsed_document",
        )

        await app.state.deadlines_collection.create_index(
            [("user_id", 1), ("source_candidate_key", 1)],
            unique=True,
            partialFilterExpression={"source_candidate_key": {"$exists": True}},
            name="unique_user_parsed_deadline_candidate",
        )

        yield
    finally:
        await client.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET"),
)

oauth = OAuth()

oauth.register(
    name="appid",
    client_id=os.getenv("APPID_CLIENT_ID"),
    client_secret=os.getenv("APPID_CLIENT_SECRET"),
    server_metadata_url=os.getenv("APPID_DISCOVERY_ENDPOINT"),
    client_kwargs={"scope": "openid profile email"},
)


def get_user(request: Request):
    user = request.session.get("user")

    if not user or not user.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    return user


@app.get("/auth/login")
async def login(request: Request):
    return await oauth.appid.authorize_redirect(
        request, "http://127.0.0.1:8000/auth/callback"
    )


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.appid.authorize_access_token(request)
        request.session["user"] = token.get("userinfo")
        return RedirectResponse("/dashboard")
    except OAuthError:
        return RedirectResponse("/auth/login")


@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/me")
async def get_current_user(request: Request):
    user = request.session.get("user")

    if not user:
        return JSONResponse(
            content={"authenticated": False, "message": "Not authenticated"},
            status_code=401,
        )

    return {"authenticated": True, "user": user}


@app.get("/api/storage")
async def get_storage_usage(request: Request):
    user = get_user(request)

    try:
        usage = await request.app.state.storage_usage_collection.find_one(
            {"user_id": user["sub"]},
            {"_id": 0, "used_bytes": 1},
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve storage usage.",
        )

    used_bytes = usage["used_bytes"] if usage else 0

    return {
        "used_bytes": used_bytes,
        "limit_bytes": MAX_STORAGE_SIZE,
        "used_percent": round(
            used_bytes / MAX_STORAGE_SIZE * 100, 2
        ),
    }


@app.post("/api/courses", status_code=201)
async def create_course(course: CourseCreate, request: Request):
    user = get_user(request)
    course_data = course.model_dump()
    course_data["user_id"] = user["sub"]

    try:
        result = await request.app.state.courses_collection.insert_one(
            course_data
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="You already have a course with this course code.",
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to create the course. Please try again.",
        )

    return {
        "message": "Course created successfully.",
        "course_id": str(result.inserted_id),
    }


@app.get("/api/courses")
async def get_courses(request: Request):
    user = get_user(request)

    try:
        courses = await request.app.state.courses_collection.find(
            {"user_id": user["sub"]}
        ).to_list(length=None)
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve courses. Please try again.",
        )

    for course in courses:
        course["id"] = str(course.pop("_id"))

    return {"courses": courses}


@app.post("/api/deadlines", status_code=201)
async def create_deadline(deadline: DeadlineCreate, request: Request):
    user = get_user(request)
    deadline_data = deadline.model_dump()
    course_id = deadline_data["course_id"]

    if course_id is not None:
        if not ObjectId.is_valid(course_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid course ID.",
            )

        try:
            course = await request.app.state.courses_collection.find_one(
                {
                    "_id": ObjectId(course_id),
                    "user_id": user["sub"],
                },
                {"_id": 1},
            )
        except PyMongoError:
            raise HTTPException(
                status_code=500,
                detail="Unable to validate the course. Please try again.",
            )

        if not course:
            raise HTTPException(
                status_code=404,
                detail="Course not found.",
            )

    deadline_data["user_id"] = user["sub"]
    deadline_data["created_at"] = datetime.now(timezone.utc)

    try:
        result = await request.app.state.deadlines_collection.insert_one(
            deadline_data
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to create the deadline. Please try again.",
        )

    return {
        "message": "Deadline created successfully.",
        "deadline_id": str(result.inserted_id),
    }


@app.post("/api/documents/{document_id}/deadlines", status_code=200)
async def add_parsed_deadlines(document_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body.")

    selected_indices = payload.get("selected_indices")
    course_id = payload.get("course_id")

    if (
        not isinstance(selected_indices, list)
        or not selected_indices
        or any(type(index) is not int or index < 0 for index in selected_indices)
    ):
        raise HTTPException(
            status_code=400,
            detail="Select at least one valid parsed deadline.",
        )

    selected_indices = list(dict.fromkeys(selected_indices))

    if course_id:
        if not isinstance(course_id, str) or not ObjectId.is_valid(course_id):
            raise HTTPException(status_code=400, detail="Invalid course ID.")

        try:
            course = await request.app.state.courses_collection.find_one(
                {"_id": ObjectId(course_id), "user_id": user["sub"]},
                {"_id": 1},
            )
        except PyMongoError as exc:
            raise HTTPException(
                status_code=500,
                detail="Unable to validate the course. Please try again.",
            ) from exc

        if not course:
            raise HTTPException(status_code=404, detail="Course not found.")

    try:
        parsed_document = await request.app.state.parsed_documents_collection.find_one(
            {"user_id": user["sub"], "document_id": document_id}
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve parsed results.",
        ) from exc

    if not parsed_document:
        raise HTTPException(status_code=404, detail="Parsed document not found.")

    candidates = parsed_document.get("parsed_data", {}).get("deadlines", [])
    if any(index >= len(candidates) for index in selected_indices):
        raise HTTPException(
            status_code=400,
            detail="One or more selected deadlines do not exist in the parsed result.",
        )

    added_indices = set(parsed_document.get("added_deadline_indices", []))
    added = []
    already_added = []
    failed = []

    for index in selected_indices:
        candidate = candidates[index]
        title = candidate.get("title")
        due_date = candidate.get("due_date")

        if not isinstance(title, str) or not title.strip():
            failed.append({"index": index, "reason": "Deadline title is missing."})
            continue

        try:
            parsed_date = datetime.strptime(due_date, "%Y-%m-%d").date()
            if parsed_date.isoformat() != due_date:
                raise ValueError
        except (TypeError, ValueError):
            failed.append({"index": index, "reason": "A valid due date is required."})
            continue

        if index in added_indices:
            already_added.append(index)
            continue

        due_start = datetime(
            parsed_date.year, parsed_date.month, parsed_date.day,
            tzinfo=timezone.utc,
        )
        due_end = due_start + timedelta(days=1)
        source_key = f"{document_id}:{index}"

        try:
            # Also avoid duplicates that already exist as ordinary deadlines.
            existing = await request.app.state.deadlines_collection.find_one(
                {
                    "user_id": user["sub"],
                    "title": {"$regex": "^" + re.escape(title.strip()) + "$", "$options": "i"},
                    "due_at": {"$gte": due_start, "$lt": due_end},
                },
                {"_id": 1},
            )

            if existing:
                await request.app.state.parsed_documents_collection.update_one(
                    {"_id": parsed_document["_id"], "user_id": user["sub"]},
                    {"$addToSet": {"added_deadline_indices": index}},
                )
                added_indices.add(index)
                already_added.append(index)
                continue

            deadline_data = {
                "user_id": user["sub"],
                "title": title.strip(),
                "description": candidate.get("evidence") or "",
                "due_at": due_end - timedelta(seconds=1),
                "course_id": course_id or None,
                "status": "not_started",
                "created_at": datetime.now(timezone.utc),
                "source_candidate_key": source_key,
            }

            await request.app.state.deadlines_collection.insert_one(deadline_data)
            await request.app.state.parsed_documents_collection.update_one(
                {"_id": parsed_document["_id"], "user_id": user["sub"]},
                {"$addToSet": {"added_deadline_indices": index}},
            )
            added_indices.add(index)
            added.append(index)

        except DuplicateKeyError:
            await request.app.state.parsed_documents_collection.update_one(
                {"_id": parsed_document["_id"], "user_id": user["sub"]},
                {"$addToSet": {"added_deadline_indices": index}},
            )
            added_indices.add(index)
            already_added.append(index)
        except PyMongoError:
            failed.append({"index": index, "reason": "Unable to save this deadline."})

    return {
        "message": "Parsed deadlines processed.",
        "added_indices": added,
        "already_added_indices": already_added,
        "failed": failed,
        "added_deadline_indices": sorted(added_indices),
    }


def calculate_time_left(due_at: datetime, status: str) -> str:
    if status == "completed":
        return "Completed"

    if due_at.tzinfo is None or due_at.utcoffset() is None:
        due_at = due_at.replace(tzinfo=timezone.utc)

    difference = (due_at - datetime.now(timezone.utc)).total_seconds()
    is_overdue = difference < 0
    total_days = abs(difference) / 86400

    if total_days < 1:
        duration = "less than a day"
    elif total_days < 30:
        days = int(total_days)
        duration = f"{days} {'day' if days == 1 else 'days'}"
    elif total_days < 365:
        months = int(total_days // 30)
        duration = f"{months} {'month' if months == 1 else 'months'}"
    else:
        years = int(total_days // 365)
        duration = f"{years} {'year' if years == 1 else 'years'}"

    return f"Overdue by {duration}" if is_overdue else f"{duration} left"


@app.get("/api/deadlines")
async def get_deadlines(request: Request):
    user = get_user(request)

    try:
        deadlines = await request.app.state.deadlines_collection.find(
            {"user_id": user["sub"]}
        ).sort("due_at", 1).to_list(length=None)
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve deadlines. Please try again.",
        )

    for deadline in deadlines:
        deadline["id"] = str(deadline.pop("_id"))
        deadline.pop("user_id", None)
        deadline["time_left"] = calculate_time_left(
            deadline["due_at"], deadline["status"]
        )

    return {"deadlines": deadlines}


@app.put("/api/deadlines/{deadline_id}")
async def update_deadline(
    deadline_id: str, deadline: DeadlineCreate, request: Request
):
    user = get_user(request)

    if not ObjectId.is_valid(deadline_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid deadline ID.",
        )

    deadline_data = deadline.model_dump()
    course_id = deadline_data["course_id"]

    if course_id is not None:
        if not ObjectId.is_valid(course_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid course ID.",
            )

        try:
            course = await request.app.state.courses_collection.find_one(
                {
                    "_id": ObjectId(course_id),
                    "user_id": user["sub"],
                },
                {"_id": 1},
            )
        except PyMongoError:
            raise HTTPException(
                status_code=500,
                detail="Unable to validate the course. Please try again.",
            )

        if not course:
            raise HTTPException(
                status_code=404,
                detail="Course not found.",
            )

    try:
        result = await request.app.state.deadlines_collection.update_one(
            {
                "_id": ObjectId(deadline_id),
                "user_id": user["sub"],
            },
            {"$set": deadline_data},
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to update the deadline. Please try again.",
        )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Deadline not found.",
        )

    return {
        "message": "Deadline updated successfully.",
        "deadline_id": deadline_id,
    }


@app.delete("/api/deadlines/{deadline_id}")
async def delete_deadline(deadline_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(deadline_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid deadline ID.",
        )

    try:
        result = await request.app.state.deadlines_collection.delete_one(
            {
                "_id": ObjectId(deadline_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete the deadline. Please try again.",
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Deadline not found.",
        )

    return {"message": "Deadline deleted successfully."}


@app.delete("/api/courses/{course_id}")
async def delete_course(course_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(course_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid course ID.",
        )

    try:
        result = await request.app.state.courses_collection.delete_one(
            {
                "_id": ObjectId(course_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete the course. Please try again.",
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Course not found.",
        )

    return {"message": "Course deleted successfully."}


async def reserve_storage(collection, user_id: str, size: int) -> bool:
    try:
        await collection.update_one(
            {"user_id": user_id},
            {"$setOnInsert": {"used_bytes": 0}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass

    result = await collection.find_one_and_update(
        {
            "user_id": user_id,
            "used_bytes": {"$lte": MAX_STORAGE_SIZE - size},
        },
        {"$inc": {"used_bytes": size}},
        return_document=ReturnDocument.AFTER,
    )

    return result is not None


async def release_storage(collection, user_id: str, size: int):
    await collection.update_one(
        {
            "user_id": user_id,
            "used_bytes": {"$gte": size},
        },
        {"$inc": {"used_bytes": -size}},
    )


@app.post("/api/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
):
    user = get_user(request)
    filename = os.path.basename((file.filename or "").strip())
    extension = os.path.splitext(filename)[1].lower()
    content_type = ALLOWED_FILE_TYPES.get(extension)

    if not filename or not content_type:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload PDF, Word, PowerPoint, or Excel files.",
        )

    if file.content_type != content_type:
        raise HTTPException(
            status_code=400,
            detail="File extension and content type do not match.",
        )

    object_key = f"users/{user['sub']}/{uuid4().hex}{extension}"
    size = 0
    uploaded = False
    reserved = False

    try:
        with SpooledTemporaryFile(
            max_size=8 * 1024 * 1024, mode="w+b"
        ) as temp:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 100 MiB upload limit.",
                    )

                temp.write(chunk)

            if size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded file is empty.",
                )

            reserved = await reserve_storage(
                request.app.state.storage_usage_collection,
                user["sub"],
                size,
            )

            if not reserved:
                raise HTTPException(
                    status_code=413,
                    detail="Your 500 MiB storage limit would be exceeded.",
                )

            temp.seek(0)

            await run_in_threadpool(
                upload_file, temp, object_key, content_type
            )
            uploaded = True

        document = {
            "user_id": user["sub"],
            "filename": filename,
            "object_key": object_key,
            "content_type": content_type,
            "size": size,
            "course_ids": [],
            "uploaded_at": datetime.now(timezone.utc),
        }

        result = await request.app.state.documents_collection.insert_one(
            document
        )

    except Exception as exc:
        if uploaded:
            try:
                await run_in_threadpool(delete_file, object_key)
            except Exception:
                pass

        if reserved:
            try:
                await release_storage(
                    request.app.state.storage_usage_collection,
                    user["sub"],
                    size,
                )
            except Exception:
                pass

        if isinstance(exc, HTTPException):
            raise

        if isinstance(exc, PyMongoError):
            raise HTTPException(
                status_code=500,
                detail="Unable to save document metadata. Please try again.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Unable to upload the document. Please try again.",
        ) from exc

    finally:
        await file.close()

    return {
        "message": "Document uploaded successfully.",
        "document_id": str(result.inserted_id),
        "filename": filename,
        "size": size,
    }


@app.get("/api/documents")
async def get_documents(request: Request):
    user = get_user(request)

    try:
        documents = await request.app.state.documents_collection.find(
            {"user_id": user["sub"]}
        ).to_list(length=None)

        parsed_documents = await (
            request.app.state.parsed_documents_collection.find(
                {"user_id": user["sub"]}
            ).to_list(length=None)
        )

    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve documents. Please try again.",
        )

    parsed_by_document_id = {
        parsed["document_id"]: parsed
        for parsed in parsed_documents
    }

    for document in documents:
        document_id = str(document.pop("_id"))
        document["id"] = document_id

        parsed = parsed_by_document_id.get(document_id)

        document["is_parsed"] = parsed is not None
        document["parsed_data"] = (
            parsed["parsed_data"] if parsed else None
        )
        document["parsed_at"] = (
            parsed["parsed_at"] if parsed else None
        )
        document["added_deadline_indices"] = (
            parsed.get("added_deadline_indices", []) if parsed else []
        )

    return {"documents": documents}


@app.get("/api/documents/{document_id}/download")
async def download_document(document_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(document_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID.",
        )

    try:
        document = await request.app.state.documents_collection.find_one(
            {
                "_id": ObjectId(document_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve document metadata.",
        )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    try:
        file_stream = await run_in_threadpool(
            download_file, document["object_key"]
        )
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve the document from storage.",
        )

    filename = os.path.basename(document["filename"])

    return StreamingResponse(
        file_stream,
        media_type=document["content_type"],
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(file_stream.close),
    )

@app.post("/api/documents/{document_id}/parse")
async def parse_uploaded_document(document_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(document_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID.",
        )

    try:
        document = await request.app.state.documents_collection.find_one(
            {
                "_id": ObjectId(document_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve document metadata.",
        )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    filename = os.path.basename(document["filename"])

    # Return previously parsed results without spending credits.
    try:
        saved_result = (
            await request.app.state.parsed_documents_collection.find_one(
                {
                    "user_id": user["sub"],
                    "document_id": document_id,
                }
            )
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve previously parsed results.",
        )

    if saved_result:
        return {
            "document_id": document_id,
            "filename": filename,
            "parsed_data": saved_result["parsed_data"],
        }

    extension = os.path.splitext(filename)[1].lower()

    if extension not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported document format.",
        )

    try:
        file_stream = await run_in_threadpool(
            download_file, document["object_key"]
        )
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve the document from storage.",
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=extension,
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            await run_in_threadpool(
                shutil.copyfileobj,
                file_stream,
                temp_file,
            )

        parsed_result = await run_in_threadpool(
            parse_document,
            temp_path,
        )

        parsed_document = {
            "user_id": user["sub"],
            "document_id": document_id,
            "filename": filename,
            "parsed_data": parsed_result,
            "parsed_at": datetime.now(timezone.utc),
        }

        await request.app.state.parsed_documents_collection.insert_one(
            parsed_document
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "parsed_data": parsed_result,
        }

    except HTTPException:
        raise

    except PyMongoError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to save the parsed results.",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to parse the document. "
                "Please check the file format and try again."
            ),
        ) from exc

    finally:
        file_stream.close()

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str, request: Request):
    user = get_user(request)

    if not ObjectId.is_valid(document_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID.",
        )

    documents = request.app.state.documents_collection
    parsed_documents = request.app.state.parsed_documents_collection
    storage_usage = request.app.state.storage_usage_collection

    try:
        document = await documents.find_one(
            {
                "_id": ObjectId(document_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve document metadata.",
        )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    try:
        await run_in_threadpool(delete_file, document["object_key"])
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=502,
            detail="Unable to delete the document from storage.",
        )

    async def delete_metadata_and_release_storage(session):
        result = await documents.delete_one(
            {
                "_id": document["_id"],
                "user_id": user["sub"],
            },
            session=session,
        )

        if result.deleted_count != 1:
            raise HTTPException(
                status_code=404,
                detail="Document metadata not found.",
            )

        await parsed_documents.delete_one(
            {
                "user_id": user["sub"],
                "document_id": document_id,
            },
            session=session,
        )

        usage_result = await storage_usage.update_one(
            {
                "user_id": user["sub"],
                "used_bytes": {"$gte": document["size"]},
            },
            {"$inc": {"used_bytes": -document["size"]}},
            session=session,
        )

        if usage_result.modified_count != 1:
            raise RuntimeError(
                "Storage counter is missing or inconsistent."
            )

    try:
        async with request.app.state.mongodb_client.start_session() as session:
            await session.with_transaction(
                delete_metadata_and_release_storage
            )
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail=(
                "The file was deleted from storage, but database changes "
                "could not be completed. Please retry the deletion."
            ),
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail=(
                "The file was deleted from storage, but storage accounting "
                "needs reconciliation."
            ),
        )

    return {"message": "Document deleted successfully."}


@app.get("/dashboard")
async def dashboard(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/auth/login")

    return FileResponse("protected/dashboard.html")


@app.get("/dashboard.css")
async def dashboard_css(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/auth/login")

    return FileResponse("protected/dashboard.css")


@app.get("/dashboard.js")
async def dashboard_js(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/auth/login")

    return FileResponse("protected/dashboard.js")


app.mount("/", StaticFiles(directory="public", html=True), name="public")
 