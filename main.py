
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from database import create_mongodb_client, DATABASE_NAME
from models import CourseCreate
from storage import upload_file, download_file, delete_file


load_dotenv()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB

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

        await client.admin.command("ping")

        await app.state.courses_collection.create_index(
            [("user_id", 1), ("course_code", 1)],
            unique=True,
            name="unique_user_course_code",
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

    except HTTPException:
        raise
    except PyMongoError:
        if uploaded:
            try:
                await run_in_threadpool(delete_file, object_key)
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail="Unable to save document metadata. Please try again.",
        )
    except Exception:
        if uploaded:
            try:
                await run_in_threadpool(delete_file, object_key)
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail="Unable to upload the document. Please try again.",
        )
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
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve documents. Please try again.",
        )

    for document in documents:
        document["id"] = str(document.pop("_id"))

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

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str, request: Request):
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
        await run_in_threadpool(delete_file, document["object_key"])
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=502,
            detail="Unable to delete the document from storage.",
        )

    try:
        result = await request.app.state.documents_collection.delete_one(
            {
                "_id": ObjectId(document_id),
                "user_id": user["sub"],
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=500,
            detail=(
                "The file was deleted from storage, "
                "but its metadata could not be deleted."
            ),
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Document metadata not found.",
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
