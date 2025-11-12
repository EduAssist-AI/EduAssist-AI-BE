from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.video import VideoUploadResponse # Reusing for status response
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# Enhanced response model for video processing status
class VideoProcessingStatus(BaseModel):
    videoId: str
    status: str
    progress: Optional[int] = None
    currentStep: Optional[str] = None
    estimatedTimeRemaining: Optional[int] = None
    error: Optional[str] = None

@router.get("/videos/{videoId}/status", response_model=VideoProcessingStatus, status_code=status.HTTP_200_OK)
async def get_video_processing_status(
    videoId: str,
    current_user=Depends(get_current_user)
):
    # 1. Validate video existence
    video_obj_id = ObjectId(videoId)
    video = await db["videos"].find_one({"_id": video_obj_id})
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    
    # 2. Check user permissions (only course owner or enrolled students can see status)
    # Check if user has access to the course this video belongs to
    course = await db["course_rooms"].find_one({"_id": video["course_id"]})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    
    # Check if current user is course owner or enrolled
    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": video["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this video."
        )
    
    # 3. Return current status with additional details
    status_response = {
        "videoId": str(video["_id"]),
        "status": video["status"]
    }
    
    # Add additional fields based on status
    if video["status"] == "PROCESSING":
        status_response["progress"] = video.get("progress", 0)
        status_response["currentStep"] = video.get("current_step", "Initializing")
        status_response["estimatedTimeRemaining"] = video.get("estimated_time_remaining", 180)
    
    if video["status"] == "FAILED":
        status_response["error"] = video.get("error_message", "Processing failed")
    
    return VideoProcessingStatus(**status_response)