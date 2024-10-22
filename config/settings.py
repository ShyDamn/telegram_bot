# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    SESSION_API_URL = os.getenv("SESSION_API_URL", "http://localhost:8000")

settings = Settings()
