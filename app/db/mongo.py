from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DB_NAME]
chat_history_collection = db["chat_history"]

