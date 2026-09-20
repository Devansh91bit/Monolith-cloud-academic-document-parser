import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is missing from .env")

client = AsyncIOMotorClient(MONGODB_URI)

db = client["monolith_db"]

courses_collection = db["courses"]
documents_collection = db["documents"]
deadlines_collection = db["deadlines"]