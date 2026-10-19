
import os
from contextlib import asynccontextmanager

from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.middleware.sessions import SessionMiddleware

from database import create_mongodb_client, DATABASE_NAME
from models import CourseCreate

load_dotenv()


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
    user = request.session.get("user")

    if not user or not user.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

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
