from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class CourseCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)

class CourseCreateResponse(BaseModel):
    courseId: str
    name: str
    description: str
    invitationCode: str
    invitationLink: str
    createdAt: datetime
    status: Literal["ACTIVE", "ARCHIVED"]

class CourseJoinRequest(BaseModel):
    invitationCode: str = Field(..., min_length=1, max_length=8)

class CourseJoinResponse(BaseModel):
    enrollmentId: str
    courseId: str
    courseName: str
    role: Literal["STUDENT"]
    joinedAt: datetime

class CourseListQuery(BaseModel):
    status: Optional[Literal["ACTIVE", "ARCHIVED"]] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

class CourseListResponse(BaseModel):
    courses: list
    pagination: dict