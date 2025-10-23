from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/courses/{course_id}/modules/{module_id}/videos", status_code=status.HTTP_202_ACCEPTED)
async def upload_video_to_module(
    course_id: str,
    module_id: str,
    file: UploadFile = File(...),
    title: str = None,
    current_user=Depends(get_current_user)
):
    # Check if the user is the course owner (faculty)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found."
        )
    
    # Verify module exists and belongs to course
    module = await db["modules"].find_one({
        "_id": ObjectId(module_id),
        "course_id": ObjectId(course_id)
    })
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found in this course."
        )
    
    if str(course["created_by"]) != current_user["_id"] or current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can upload videos to modules."
        )
    
    # Validate file type
    allowed_extensions = ['.mp4', '.avi', '.mov']
    file_extension = '.' + file.filename.split('.')[-1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported video format (only MP4, AVI, MOV)."
        )
    
    # Validate file size (2GB limit)
    if file.size and file.size > 2 * 1024 * 1024 * 1024:  # 2GB in bytes
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 2GB limit."
        )
    
    # Default title if not provided
    if not title:
        title = file.filename
    
    video_doc = {
        "course_id": ObjectId(course_id),
        "module_id": ObjectId(module_id),  # Associate with module
        "title": title,
        "storage_url": f"temp/{file.filename}",  # placeholder for actual storage URL
        "status": "PENDING",
        "published": False,
        "duration_seconds": 0,  # will be set during processing
        "uploaded_at": datetime.utcnow(),
        "processed_at": None
    }
    
    result = await db["videos"].insert_one(video_doc)
    
    return {
        "videoId": str(result.inserted_id),
        "moduleId": module_id,
        "title": title,
        "status": "PENDING",
        "statusUrl": f"/api/v1/videos/{str(result.inserted_id)}/status",
        "estimatedProcessingTime": 300  # 5 minutes
    }

@router.get("/courses/{course_id}/modules/{module_id}/videos", status_code=status.HTTP_200_OK)
async def get_videos_list_for_module(
    course_id: str,
    module_id: str,
    published: bool = None,
    status_filter: str = None,
    page: int = 1,
    limit: int = 20,
    current_user=Depends(get_current_user)
):
    # Validate pagination parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    # Check if user has access to the course
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": ObjectId(course_id)
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Verify module exists
    module = await db["modules"].find_one({
        "_id": ObjectId(module_id),
        "course_id": ObjectId(course_id)
    })
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found in this course."
        )
    
    # Build query for videos in specific module
    query = {"module_id": ObjectId(module_id)}
    
    # Faculty can see all videos, students only see published ones by default
    if current_user.get('role') == 'STUDENT' and published is None:
        query["published"] = True
    elif published is not None:
        query["published"] = published
    
    if status_filter:
        query["status"] = status_filter
    
    # Get total count for pagination
    total_count = await db["videos"].count_documents(query)
    
    # Get paginated results
    videos = []
    async for video in db["videos"].find(query).skip((page - 1) * limit).limit(limit):
        # Check for associated content
        transcript = await db["transcripts"].find_one({"video_id": video["_id"]})
        summary = await db["summaries"].find_one({"video_id": video["_id"], "is_published": True})
        quiz = await db["quizzes"].find_one({"video_id": video["_id"], "is_published": True})
        
        video_data = {
            "videoId": str(video["_id"]),
            "moduleId": str(video["module_id"]),
            "title": video["title"],
            "durationSeconds": video.get("duration_seconds", 0),
            "status": video["status"],
            "published": video["published"],
            "publishedAt": video.get("published_at"),
            "thumbnailUrl": f"https://drive.google.com/.../{video.get('storage_url', 'default')}",
            "hasTranscript": transcript is not None,
            "hasSummary": summary is not None,
            "hasQuiz": quiz is not None
        }
        videos.append(video_data)
    
    return {
        "videos": videos,
        "pagination": {
            "currentPage": page,
            "totalPages": (total_count + limit - 1) // limit if limit > 0 else 1,
            "totalItems": total_count,
            "itemsPerPage": limit
        }
    }