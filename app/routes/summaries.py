from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from app.utils.summary_generator import SummaryGenerator, SummaryRequest

router = APIRouter()

@router.post("/videos/{video_id}/summaries", status_code=status.HTTP_201_CREATED)
async def generate_summary(
    video_id: str,
    request_data: SummaryRequest,
    current_user=Depends(get_current_user)
):
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
    
    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]), 
        "course_id": video["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Validate required fields
    length_type = request_data.length_type
    if length_type not in ['BRIEF', 'DETAILED', 'COMPREHENSIVE']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid length type. Must be BRIEF, DETAILED, or COMPREHENSIVE."
        )
    
    # Get the transcript for this video to generate summary
    transcript = await db["transcripts"].find_one({"video_id": ObjectId(video_id)})
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No transcript found for this video. Video must be processed first."
        )
    
    # Convert transcript segments to the required format
    from pydantic import BaseModel
    class TranscriptSegment(BaseModel):
        start: float
        end: float
        text: str

    transcript_segments = [
        TranscriptSegment(start=seg["start"], end=seg["end"], text=seg["text"])
        for seg in transcript["segments"]
    ]
    
    # Initialize summary generator and create summary
    summary_generator = SummaryGenerator()
    summary_response = await summary_generator.generate_and_store_summary(
        video_id, 
        transcript_segments, 
        length_type, 
        request_data.focus_areas
    )
    
    return {
        "summaryId": summary_response.summaryId,
        "videoId": summary_response.videoId,
        "lengthType": summary_response.lengthType,
        "content": summary_response.content,
        "wordCount": summary_response.wordCount,
        "version": summary_response.version,
        "isPublished": summary_response.isPublished,
        "createdAt": datetime.utcnow()
    }

@router.patch("/summaries/{summary_id}/publish", status_code=status.HTTP_200_OK)
async def publish_summary(summary_id: str, request_data: dict, current_user=Depends(get_current_user)):
    # Only faculty can publish
    if current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can publish content."
        )
    
    summary = await db["summaries"].find_one({"_id": ObjectId(summary_id)})
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found."
        )
    
    # Get the video to verify access
    video = await db["videos"].find_one({"_id": summary["video_id"]})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated video not found."
        )
    
    # Verify faculty is course owner
    course = await db["course_rooms"].find_one({"_id": video["course_id"]})
    if not course or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    is_published = request_data.get('isPublished', True)
    
    await db["summaries"].update_one(
        {"_id": ObjectId(summary_id)},
        {"$set": {"is_published": is_published, "published_at": datetime.utcnow() if is_published else None}}
    )
    
    return {
        "summaryId": summary_id,
        "isPublished": is_published,
        "publishedAt": datetime.utcnow() if is_published else None,
        "version": summary.get("version", 1)
    }