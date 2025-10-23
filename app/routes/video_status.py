from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId

router = APIRouter()

@router.get("/videos/{video_id}/status", status_code=status.HTTP_200_OK)
async def get_video_processing_status(video_id: str, current_user=Depends(get_current_user)):
    video = await db["videos"].find_one({"_id": ObjectId(video_id)})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found."
        )
    
    # Check if user has access (course owner or enrolled student)
    course = await db["course_rooms"].find_one({"_id": video["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": video["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # In a real implementation, this would check actual processing progress
    # For now, return a static status based on the video's status
    status_info = {
        "videoId": video_id,
        "status": video["status"],
        "progress": 100 if video["status"] == "COMPLETE" else 0,
        "currentStep": "Processing completed" if video["status"] == "COMPLETE" else "Queued for processing",
        "estimatedTimeRemaining": 0,
        "error": None
    }
    
    if video["status"] == "FAILED":
        status_info["error"] = "Processing failed"
    
    return status_info