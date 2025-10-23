from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class ModuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)

class ModuleResponse(BaseModel):
    moduleId: str
    courseId: str
    name: str
    description: str
    createdAt: datetime
    status: Literal["ACTIVE", "INACTIVE"]

class ModuleListResponse(BaseModel):
    modules: list