from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class VideoUploadRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)

class VideoUploadResponse(BaseModel):
    videoId: str
    title: str
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED"]
    statusUrl: str
    estimatedProcessingTime: Optional[int] = None

class VideoOut(BaseModel):
    videoId: str = Field(..., alias="id")
    title: str
    durationSeconds: Optional[int] = None
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED"]
    published: bool
    publishedAt: Optional[datetime] = None
    thumbnailUrl: Optional[str] = None
    hasTranscript: bool
    hasSummary: bool
    hasQuiz: bool

class VideoListResponse(BaseModel):
    videos: list[VideoOut]
    pagination: dict