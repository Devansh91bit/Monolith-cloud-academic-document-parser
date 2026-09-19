import os
from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

app = FastAPI()

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