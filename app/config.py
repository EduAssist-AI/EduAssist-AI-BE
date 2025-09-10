# app/config.py
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from `.env`

class Settings(BaseSettings):
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DB_NAME: str = os.getenv("DB_NAME", "EduAssistAI")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "93Ivws/VxpsGhy5MBveFeTnGUB2lvRJhFwrUmUzbAbQ=")

settings = Settings()
