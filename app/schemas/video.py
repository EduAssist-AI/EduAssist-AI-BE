from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class ResourceUploadRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)

class ResourceUploadResponse(BaseModel):
    resourceId: str
    title: str
    type: str  # New field to store file type
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED"]
    statusUrl: str
    estimatedProcessingTime: Optional[int] = None

# Backward compatibility - keep original video types
class VideoUploadResponse(BaseModel):
    videoId: str
    title: str
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED"]
    statusUrl: str
    estimatedProcessingTime: Optional[int] = None

class ResourceOut(BaseModel):
    resourceId: str = Field(..., alias="id")
    title: str
    type: str  # New field to store file type
    durationSeconds: Optional[int] = None  # Only for video resources
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED"]
    published: bool
    publishedAt: Optional[datetime] = None
    thumbnailUrl: Optional[str] = None
    hasTranscript: bool
    hasSummary: bool
    hasQuiz: bool

# Backward compatibility for video endpoints
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

class ResourceListResponse(BaseModel):
    resources: list[ResourceOut]
    pagination: dict

# Backward compatibility for video endpoints
class VideoListResponse(BaseModel):
    videos: list[VideoOut]
    pagination: dict