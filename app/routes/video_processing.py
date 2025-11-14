"""
API endpoints for EduAssist-AI video processing with full CRUD operations
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status, Body
from typing import Optional, List
import os
import uuid
from pathlib import Path
from app.utils.auth import get_current_user
from app.schemas.user import UserOut
from app.db.mongo import db
from bson import ObjectId
import datetime

from app.utils.audio_processor import AudioProcessor
from app.rag.generator import TranscriptSegment, add_video_content_to_rag

router = APIRouter()
processor = AudioProcessor()

@router.post("/transcribe-video/")
async def transcribe_video_endpoint(video: UploadFile = File(...)):
    """
    Upload a video file and get its transcription
    
    Args:
        video: Video file to transcribe (MP4, AVI, MOV, etc.)
        
    Returns:
        dict: Contains the transcription result
    """
    try:
        # Validate file type
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv', '.webm'}
        file_ext = Path(video.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not supported. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Create uploads directory if needed
        upload_dir = Path("uploads") / "videos"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file temporarily
        temp_video_path = upload_dir / f"temp_{uuid.uuid4()}_{video.filename}"
        with open(temp_video_path, "wb") as f:
            f.write(await video.read())
        
        # Process the video
        transcription = processor.process_video_for_transcription(str(temp_video_path))
        
        # Clean up the uploaded video file
        if temp_video_path.exists():
            os.unlink(temp_video_path)
        
        if transcription is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to process video for transcription"
            )
        
        # Create a simple transcript segment from the full transcription
        transcript_segments = [TranscriptSegment(start=0.0, end=30.0, text=transcription)]
        
        # Add to RAG system for semantic search
        video_id = str(uuid.uuid4())
        await add_video_content_to_rag(video_id, "transcript_1", transcript_segments)
        
        return {
            "success": True,
            "video_id": video_id,
            "video_filename": video.filename,
            "transcription_length": len(transcription),
            "transcription": transcription,
            "transcript_segments": transcript_segments
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing video: {str(e)}"
        )


@router.get("/videos/{video_id}")
async def get_video(video_id: str, current_user: UserOut = Depends(get_current_user)):
    """
    Get video details by ID
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found"
            )
        
        # Check if user has access (course owner or enrolled student)
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course:
            raise HTTPException(
                status_code=404,
                detail="Video course not found"
            )
        
        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]), 
            "course_id": video["course_id"]
        }) is not None
        
        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )
        
        # Convert ObjectId to string for JSON serialization
        video["_id"] = str(video["_id"])
        if "course_id" in video:
            video["course_id"] = str(video["course_id"])
        
        return video
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving video: {str(e)}"
        )


@router.put("/videos/{video_id}")
async def update_video(video_id: str, title: str = None, published: bool = None, current_user: UserOut = Depends(get_current_user)):
    """
    Update video details (title, published status)
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found"
            )
        
        # Only course owner can update the video
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=403,
                detail="Only course owner can update video details"
            )
        
        update_data = {}
        if title is not None:
            update_data["title"] = title
        if published is not None:
            update_data["published"] = published
            if published:
                update_data["published_at"] = datetime.datetime.utcnow()
        
        if update_data:
            await db["videos"].update_one(
                {"_id": ObjectId(video_id)},
                {"$set": update_data}
            )
        
        # Return updated video info
        updated_video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        updated_video["_id"] = str(updated_video["_id"])
        if "course_id" in updated_video:
            updated_video["course_id"] = str(updated_video["course_id"])
        
        return updated_video
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating video: {str(e)}"
        )


@router.delete("/videos/{video_id}")
async def delete_video(video_id: str, current_user: UserOut = Depends(get_current_user)):
    """
    Delete video by ID (only course owner)
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found"
            )
        
        # Only course owner can delete the video
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=403,
                detail="Only course owner can delete video"
            )
        
        # Delete related documents
        # 1. Delete transcript if it exists
        await db["transcripts"].delete_many({"video_id": ObjectId(video_id)})
        
        # 2. Delete summaries if they exist
        await db["summaries"].delete_many({"video_id": ObjectId(video_id)})
        
        # 3. Delete video itself
        delete_result = await db["videos"].delete_one({"_id": ObjectId(video_id)})
        
        if delete_result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Video could not be deleted"
            )
        
        # If video was stored locally, delete the file
        if video.get("storage_type") == "local" and video.get("storage_url"):
            try:
                if os.path.exists(video["storage_url"]):
                    os.remove(video["storage_url"])
            except Exception as e:
                # Log the error but don't fail the deletion
                print(f"Warning: Could not delete local video file {video['storage_url']}: {e}")
        
        return {
            "message": "Video and related content deleted successfully",
            "deleted_video_id": video_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting video: {str(e)}"
        )


@router.get("/videos/{video_id}/transcript")
async def get_video_transcript(video_id: str, current_user: UserOut = Depends(get_current_user)):
    """
    Get transcript for a specific video
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found."
            )
        
        # Check if user has access (course owner or enrolled student)
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course:
            raise HTTPException(
                status_code=404,
                detail="Video course not found."
            )
        
        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]), 
            "course_id": video["course_id"]
        }) is not None
        
        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=403,
                detail="Access denied."
            )
        
        transcript = await db["transcripts"].find_one({"video_id": ObjectId(video_id)})
        if not transcript:
            raise HTTPException(
                status_code=404,
                detail="No transcript found for this video."
            )
        
        # Convert ObjectId to string for JSON serialization
        transcript["_id"] = str(transcript["_id"])
        transcript["video_id"] = str(transcript["video_id"])
        
        return transcript
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving transcript: {str(e)}"
        )


@router.put("/videos/{video_id}/transcript")
async def update_video_transcript(video_id: str, segments: List[dict] = Body(...), current_user: UserOut = Depends(get_current_user)):
    """
    Update video transcript segments
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found."
            )
        
        # Only course owner can update transcript
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=403,
                detail="Only course owner can update video transcript."
            )
        
        # Validate transcript segments
        for segment in segments:
            if "start" not in segment or "end" not in segment or "text" not in segment:
                raise HTTPException(
                    status_code=400,
                    detail="Each segment must have 'start', 'end', and 'text' fields"
                )
        
        # Update or create transcript document
        transcript_doc = {
            "video_id": ObjectId(video_id),
            "segments": segments,
            "updated_at": datetime.utcnow()
        }
        
        # Check if transcript already exists
        existing_transcript = await db["transcripts"].find_one({"video_id": ObjectId(video_id)})
        if existing_transcript:
            # Update existing transcript
            await db["transcripts"].update_one(
                {"video_id": ObjectId(video_id)},
                {"$set": transcript_doc}
            )
        else:
            # Create new transcript
            result = await db["transcripts"].insert_one(transcript_doc)
        
        return {
            "message": "Transcript updated successfully",
            "video_id": video_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating transcript: {str(e)}"
        )


@router.delete("/videos/{video_id}/transcript")
async def delete_video_transcript(video_id: str, current_user: UserOut = Depends(get_current_user)):
    """
    Delete transcript for a specific video
    """
    try:
        video = await db["videos"].find_one({"_id": ObjectId(video_id)})
        if not video:
            raise HTTPException(
                status_code=404,
                detail="Video not found."
            )
        
        # Only course owner can delete transcript
        course = await db["course_rooms"].find_one({"_id": video["course_id"]})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=403,
                detail="Only course owner can delete video transcript."
            )
        
        # Delete transcript
        delete_result = await db["transcripts"].delete_one({"video_id": ObjectId(video_id)})
        
        if delete_result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Transcript not found or could not be deleted."
            )
        
        return {
            "message": "Transcript deleted successfully",
            "video_id": video_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting transcript: {str(e)}"
        )


@router.post("/extract-text-from-video/")
async def extract_text_from_video_endpoint(video: UploadFile = File(...)):
    """
    Alternative endpoint name for the same functionality
    """
    return await transcribe_video_endpoint(video)