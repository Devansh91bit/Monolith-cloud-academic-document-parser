import os

from dotenv import load_dotenv
from pymongo import AsyncMongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is missing from .env")

DATABASE_NAME = "monolith_db"

def create_mongodb_client():
    return AsyncMongoClient(MONGODB_URI)