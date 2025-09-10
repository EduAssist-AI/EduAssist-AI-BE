from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ChatMessage(BaseModel):
    sender: str # e.g., "user", "llm"
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatHistory(BaseModel):
    userId: str
    messages: List[ChatMessage] = []

class ChatHistoryOut(ChatHistory):
    id: str = Field(..., alias="_id")