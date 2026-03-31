from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime

class SummaryCreate(BaseModel):
    """Request model for creating a summary"""
    content: str = Field(..., min_length=1, description="The summary content")
    length_type: Literal["BRIEF", "DETAILED", "COMPREHENSIVE"] = "BRIEF"
    focus_areas: List[str] = Field(default_factory=list, description="Areas to focus on in the summary")
    custom_prompt: Optional[str] = None
    is_published: bool = False
    video_id: Optional[str] = None
    resource_id: Optional[str] = None

class SummaryUpdate(BaseModel):
    """Request model for updating a summary"""
    content: Optional[str] = None
    length_type: Optional[Literal["BRIEF", "DETAILED", "COMPREHENSIVE"]] = None
    focus_areas: Optional[List[str]] = None
    is_published: Optional[bool] = None
    version: Optional[int] = None

class SummaryResponse(BaseModel):
    """Response model for summary operations"""
    summaryId: str
    videoId: Optional[str] = None
    resourceId: Optional[str] = None
    moduleId: Optional[str] = None
    courseId: Optional[str] = None
    lengthType: str
    content: str
    wordCount: int
    version: int
    isPublished: bool
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    focusAreas: List[str] = []

    class Config:
        # Allow extra fields for backward compatibility with existing responses
        extra = "allow"

class SummaryListResponse(BaseModel):
    """Response model for listing summaries"""
    summaries: list[SummaryResponse]
    pagination: dict

class SummaryModuleListResponse(BaseModel):
    """Response model for listing summaries by module"""
    moduleId: str
    summaries: list[SummaryResponse]
    pagination: dict