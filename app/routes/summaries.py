from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from app.utils.summary_generator import SummaryGenerator, SummaryRequest
from app.rag.generator import TranscriptSegment
from app.schemas.summary import SummaryCreate, SummaryUpdate, SummaryResponse, SummaryListResponse, SummaryModuleListResponse
import logging

router = APIRouter()

@router.post("/videos/{video_id}/summaries", status_code=status.HTTP_201_CREATED, response_model=SummaryResponse)
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
    transcript_segments = [
        TranscriptSegment(start=seg["start"], end=seg["end"], text=seg["text"])
        for seg in transcript["segments"]
    ]

    # Get module_id if video is associated with a module
    module_id = str(video.get("module_id")) if video.get("module_id") else None
    course_id = str(video["course_id"])

    # Initialize summary generator and create summary with module information
    summary_generator = SummaryGenerator()
    summary_response = await summary_generator.generate_and_store_summary(
        video_id,
        transcript_segments,
        length_type,
        request_data.focus_areas,
        module_id=module_id
    )

    # Return properly formatted SummaryResponse
    return SummaryResponse(
        summaryId=summary_response.summaryId,
        videoId=summary_response.videoId,
        moduleId=module_id,
        courseId=course_id,
        lengthType=summary_response.lengthType,
        content=summary_response.content,
        wordCount=summary_response.wordCount,
        version=summary_response.version,
        isPublished=summary_response.isPublished,
        createdAt=datetime.utcnow(),
        focusAreas=request_data.focus_areas
    )


@router.post("/resources/{resource_id}/summaries", status_code=status.HTTP_201_CREATED, response_model=SummaryResponse)
async def generate_resource_summary(
    resource_id: str,
    request_data: dict,  # Using dict to accept custom prompt and other parameters
    current_user=Depends(get_current_user)
):
    resource = await db["resources"].find_one({"_id": ObjectId(resource_id)})
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found."
        )

    # Check if user has access (course owner or enrolled student)
    course = await db["course_rooms"].find_one({"_id": resource["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource course not found."
        )

    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": resource["course_id"]
    }) is not None

    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    # Extract parameters from request
    length_type = request_data.get("length_type", "BRIEF")
    focus_areas = request_data.get("focus_areas", [])
    custom_prompt = request_data.get("custom_prompt", None)

    if length_type not in ['BRIEF', 'DETAILED', 'COMPREHENSIVE']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid length type. Must be BRIEF, DETAILED, or COMPREHENSIVE."
        )

    # Get the transcript for this resource to generate summary
    transcript = await db["transcripts"].find_one({"resource_id": ObjectId(resource_id)})
    if not transcript:
        # Try to find with video_id field for backwards compatibility
        transcript = await db["transcripts"].find_one({"video_id": ObjectId(resource_id)})
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No transcript found for this resource. Resource must be processed first."
            )

    # Convert transcript segments to the required format
    transcript_segments = [
        TranscriptSegment(start=seg["start"], end=seg["end"], text=seg["text"])
        for seg in transcript["segments"]
    ]

    # Get module_id if resource is associated with a module
    module_id = str(resource.get("module_id")) if resource.get("module_id") else None
    course_id = str(resource["course_id"])

    # Initialize summary generator and create summary with module information
    summary_generator = SummaryGenerator()
    summary_response = await summary_generator.generate_and_store_resource_summary(
        resource_id,
        transcript_segments,
        length_type,
        focus_areas,
        custom_prompt,
        module_id=module_id
    )

    # Return properly formatted SummaryResponse
    return SummaryResponse(
        summaryId=summary_response.summaryId,
        resourceId=summary_response.videoId,  # Using videoId field as resourceId for compatibility
        moduleId=module_id,
        courseId=course_id,
        lengthType=summary_response.lengthType,
        content=summary_response.content,
        wordCount=summary_response.wordCount,
        version=summary_response.version,
        isPublished=summary_response.isPublished,
        createdAt=datetime.utcnow(),
        focusAreas=focus_areas
    )

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

    # Get the video or resource to verify access
    video = None
    resource = None

    if summary.get("video_id"):
        video = await db["videos"].find_one({"_id": summary["video_id"]})
    elif summary.get("resource_id"):
        resource = await db["resources"].find_one({"_id": summary["resource_id"]})

    # Determine the course from either video or resource
    course_id = None
    if video:
        course_id = video["course_id"]
    elif resource:
        course_id = resource["course_id"]
    else:
        # Try to get course_id directly from summary
        course_id = summary.get("course_id")

    if not course_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated course not found."
        )

    # Verify faculty is course owner
    course = await db["course_rooms"].find_one({"_id": course_id})
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


@router.get("/resources/{course_id}/resources-with-summaries", status_code=status.HTTP_200_OK)
async def get_resources_with_summaries(
    course_id: str,
    current_user=Depends(get_current_user)
):
    """
    Get all resources for a course with their summary status
    """
    from bson import ObjectId

    # Check if user has access (course owner or enrolled student)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found."
        )

    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": ObjectId(course_id)
    }) is not None

    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    # Get all resources for this course
    resources = []
    resource_cursor = db["resources"].find({"course_id": ObjectId(course_id)})
    async for resource in resource_cursor:
        resource_id = str(resource["_id"])

        # Check if there's a summary for this resource
        summary = await db["summaries"].find_one({
            "$or": [
                {"resource_id": ObjectId(resource_id)},
                {"video_id": ObjectId(resource_id)}
            ]
        })

        resource_data = {
            "resourceId": resource_id,
            "title": resource["title"],
            "type": resource["type"],
            "status": resource["status"],
            "hasSummary": summary is not None,
            "summaryId": str(summary["_id"]) if summary else None,
            "summaryContent": summary["content"] if summary else None,
            "summaryLengthType": summary["length_type"] if summary else None,
            "isPublished": summary["is_published"] if summary and "is_published" in summary else False,
            "createdAt": resource.get("uploaded_at", datetime.utcnow()),
            "hasTranscript": await db["transcripts"].find_one({
                "$or": [
                    {"resource_id": ObjectId(resource_id)},
                    {"video_id": ObjectId(resource_id)}
                ]
            }) is not None
        }

        resources.append(resource_data)

    return {
        "courseId": course_id,
        "resources": resources,
        "totalResources": len(resources)
    }


# NEW CRUD ENDPOINTS FOR SUMMARIES

@router.post("/summaries", status_code=status.HTTP_201_CREATED, response_model=SummaryResponse)
async def create_summary(
    summary_data: SummaryCreate,
    current_user=Depends(get_current_user)
):
    """
    Create a new summary with module association
    """
    try:
        # Validate required fields
        if not summary_data.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content is required to create a summary"
            )

        # Check if the user has access to create summaries based on the video/resource
        video_id = summary_data.video_id
        resource_id = summary_data.resource_id

        # Determine which content type we're working with
        content_id = None
        content_type = None
        course_id = None
        module_id = None

        if video_id:
            video = await db["videos"].find_one({"_id": ObjectId(video_id)})
            if not video:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found."
                )
            content_id = video_id
            content_type = "video"
            course_id = str(video["course_id"])
            module_id = str(video.get("module_id")) if video.get("module_id") else None
        elif resource_id:
            resource = await db["resources"].find_one({"_id": ObjectId(resource_id)})
            if not resource:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Resource not found."
                )
            content_id = resource_id
            content_type = "resource"
            course_id = str(resource["course_id"])
            module_id = str(resource.get("module_id")) if resource.get("module_id") else None
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either video_id or resource_id is required"
            )

        # Verify user has access to the course
        course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found."
            )

        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        }) is not None

        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied."
            )

        # Create summary document
        summary_doc = {
            "length_type": summary_data.length_type,
            "content": summary_data.content,
            "word_count": len(summary_data.content.split()),
            "version": 1,
            "is_published": summary_data.is_published,
            "focus_areas": summary_data.focus_areas or [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        }

        # Add module_id if available
        if module_id:
            summary_doc["module_id"] = ObjectId(module_id)

        # Add video_id or resource_id based on content type
        if content_type == "video":
            summary_doc["video_id"] = ObjectId(content_id)
        elif content_type == "resource":
            summary_doc["resource_id"] = ObjectId(content_id)

        result = await db["summaries"].insert_one(summary_doc)
        summary_id = str(result.inserted_id)

        # Return the created summary
        return SummaryResponse(
            summaryId=summary_id,
            videoId=content_id if content_type == "video" else None,
            resourceId=content_id if content_type == "resource" else None,
            moduleId=module_id,
            courseId=course_id,
            lengthType=summary_doc["length_type"],
            content=summary_doc["content"],
            wordCount=summary_doc["word_count"],
            version=summary_doc["version"],
            isPublished=summary_doc["is_published"],
            createdAt=summary_doc["created_at"],
            updatedAt=summary_doc["updated_at"],
            focusAreas=summary_doc["focus_areas"]
        )
    except Exception as e:
        logging.error(f"Error creating summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create summary: {str(e)}"
        )


@router.get("/summaries/{summary_id}", status_code=status.HTTP_200_OK, response_model=SummaryResponse)
async def get_summary(
    summary_id: str,
    current_user=Depends(get_current_user)
):
    """
    Get a specific summary by ID
    """
    try:
        summary = await db["summaries"].find_one({"_id": ObjectId(summary_id)})
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Summary not found."
            )

        # Get course_id from summary, but handle cases where it might be missing
        course_id = summary.get("course_id")

        # Try to get course_id from video or resource if not directly available
        if not course_id:
            # If summary has video_id, get course_id from video
            if summary.get("video_id"):
                video = await db["videos"].find_one({"_id": summary["video_id"]})
                if video and video.get("course_id"):
                    course_id = video["course_id"]

            # If summary has resource_id, get course_id from resource
            elif summary.get("resource_id"):
                resource = await db["resources"].find_one({"_id": summary["resource_id"]})
                if resource and resource.get("course_id"):
                    course_id = resource["course_id"]

        # If we still don't have course_id, we can't verify access
        if not course_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated course not found for summary."
            )

        # Verify user has access to the course
        course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found."
            )

        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        }) is not None

        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied."
            )

        return SummaryResponse(
            summaryId=str(summary["_id"]),
            videoId=str(summary.get("video_id")) if summary.get("video_id") else None,
            resourceId=str(summary.get("resource_id")) if summary.get("resource_id") else None,
            moduleId=str(summary.get("module_id")) if summary.get("module_id") else None,
            courseId=str(course_id) if course_id else str(summary.get("course_id")) if summary.get("course_id") else None,
            lengthType=summary["length_type"],
            content=summary["content"],
            wordCount=summary["word_count"],
            version=summary["version"],
            isPublished=summary.get("is_published", False),
            createdAt=summary["created_at"],
            updatedAt=summary.get("updated_at"),
            focusAreas=summary.get("focus_areas", [])
        )
    except Exception as e:
        logging.error(f"Error retrieving summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve summary: {str(e)}"
        )


@router.put("/summaries/{summary_id}", status_code=status.HTTP_200_OK, response_model=SummaryResponse)
async def update_summary(
    summary_id: str,
    summary_update: SummaryUpdate,
    current_user=Depends(get_current_user)
):
    """
    Update an existing summary
    """
    try:
        # Get the existing summary
        existing_summary = await db["summaries"].find_one({"_id": ObjectId(summary_id)})
        if not existing_summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Summary not found."
            )

        # Get course_id from summary, but handle cases where it might be missing
        course_id = existing_summary.get("course_id")

        # Try to get course_id from video or resource if not directly available
        if not course_id:
            # If summary has video_id, get course_id from video
            if existing_summary.get("video_id"):
                video = await db["videos"].find_one({"_id": existing_summary["video_id"]})
                if video and video.get("course_id"):
                    course_id = video["course_id"]

            # If summary has resource_id, get course_id from resource
            elif existing_summary.get("resource_id"):
                resource = await db["resources"].find_one({"_id": existing_summary["resource_id"]})
                if resource and resource.get("course_id"):
                    course_id = resource["course_id"]

        # If we still don't have course_id, we can't verify access
        if not course_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated course not found for summary."
            )

        # Verify user is course owner (faculty) to update summaries
        course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only course owner can update summaries."
            )

        if current_user.get('role') != 'FACULTY':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only faculty members can update summaries."
            )

        # Prepare update data
        update_data = {"$set": {"updated_at": datetime.utcnow()}}

        if summary_update.content:
            update_data["$set"]["content"] = summary_update.content
            update_data["$set"]["word_count"] = len(summary_update.content.split())

        if summary_update.length_type:
            update_data["$set"]["length_type"] = summary_update.length_type

        if summary_update.focus_areas is not None:
            update_data["$set"]["focus_areas"] = summary_update.focus_areas

        if summary_update.is_published is not None:
            update_data["$set"]["is_published"] = summary_update.is_published

        if summary_update.version:
            update_data["$set"]["version"] = summary_update.version

        # Update the summary
        result = await db["summaries"].update_one(
            {"_id": ObjectId(summary_id)},
            update_data
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No changes made to summary"
            )

        # Return updated summary
        updated_summary = await db["summaries"].find_one({"_id": ObjectId(summary_id)})
        return SummaryResponse(
            summaryId=str(updated_summary["_id"]),
            videoId=str(updated_summary.get("video_id")) if updated_summary.get("video_id") else None,
            resourceId=str(updated_summary.get("resource_id")) if updated_summary.get("resource_id") else None,
            moduleId=str(updated_summary.get("module_id")) if updated_summary.get("module_id") else None,
            courseId=str(course_id),
            lengthType=updated_summary["length_type"],
            content=updated_summary["content"],
            wordCount=updated_summary["word_count"],
            version=updated_summary["version"],
            isPublished=updated_summary.get("is_published", False),
            createdAt=updated_summary["created_at"],
            updatedAt=updated_summary["updated_at"],
            focusAreas=updated_summary.get("focus_areas", [])
        )
    except Exception as e:
        logging.error(f"Error updating summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update summary: {str(e)}"
        )


@router.delete("/summaries/{summary_id}", status_code=status.HTTP_200_OK)
async def delete_summary(
    summary_id: str,
    current_user=Depends(get_current_user)
):
    """
    Delete a summary by ID
    """
    try:
        # Get the existing summary
        summary = await db["summaries"].find_one({"_id": ObjectId(summary_id)})
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Summary not found."
            )

        # Get course_id from summary, but handle cases where it might be missing
        course_id = summary.get("course_id")

        # Try to get course_id from video or resource if not directly available
        if not course_id:
            # If summary has video_id, get course_id from video
            if summary.get("video_id"):
                video = await db["videos"].find_one({"_id": summary["video_id"]})
                if video and video.get("course_id"):
                    course_id = video["course_id"]

            # If summary has resource_id, get course_id from resource
            elif summary.get("resource_id"):
                resource = await db["resources"].find_one({"_id": summary["resource_id"]})
                if resource and resource.get("course_id"):
                    course_id = resource["course_id"]

        # If we still don't have course_id, we can't verify access
        if not course_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated course not found for summary."
            )

        # Verify user is course owner (faculty) to delete summaries
        course = await db["course_rooms"].find_one({"_id": course_id})
        if not course or str(course["created_by"]) != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only course owner can delete summaries."
            )

        if current_user.get('role') != 'FACULTY':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only faculty members can delete summaries."
            )

        # Delete the summary
        result = await db["summaries"].delete_one({"_id": ObjectId(summary_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Summary could not be deleted"
            )

        return {"message": "Summary deleted successfully", "summaryId": summary_id}
    except Exception as e:
        logging.error(f"Error deleting summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete summary: {str(e)}"
        )


@router.get("/modules/{module_id}/summaries", status_code=status.HTTP_200_OK, response_model=SummaryModuleListResponse)
async def get_module_summaries(
    module_id: str,
    current_user=Depends(get_current_user),
    skip: int = 0,
    limit: int = 20
):
    """
    Get all summaries for a specific module
    """
    try:
        # Validate module exists
        module = await db["modules"].find_one({"_id": ObjectId(module_id)})
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found."
            )

        # Verify user has access to the course
        course_id = str(module["course_id"])
        course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found."
            )

        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        }) is not None

        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied."
            )

        # Get summaries for this module
        summaries = []
        summary_cursor = db["summaries"].find({
            "module_id": ObjectId(module_id)
        }).skip(skip).limit(limit)

        async for summary in summary_cursor:
            summary_response = SummaryResponse(
                summaryId=str(summary["_id"]),
                videoId=str(summary.get("video_id")) if summary.get("video_id") else None,
                resourceId=str(summary.get("resource_id")) if summary.get("resource_id") else None,
                moduleId=module_id,
                courseId=str(summary.get("course_id")) if summary.get("course_id") else None,
                lengthType=summary["length_type"],
                content=summary["content"],
                wordCount=summary["word_count"],
                version=summary["version"],
                isPublished=summary.get("is_published", False),
                createdAt=summary["created_at"],
                updatedAt=summary.get("updated_at"),
                focusAreas=summary.get("focus_areas", [])
            )
            summaries.append(summary_response)

        total_count = await db["summaries"].count_documents({"module_id": ObjectId(module_id)})

        return SummaryModuleListResponse(
            moduleId=module_id,
            summaries=summaries,
            pagination={
                "total": total_count,
                "page": (skip // limit) + 1,
                "limit": limit,
                "hasNext": (skip + limit) < total_count,
                "hasPrev": skip > 0
            }
        )
    except Exception as e:
        logging.error(f"Error retrieving module summaries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve module summaries: {str(e)}"
        )


@router.get("/courses/{course_id}/summaries", status_code=status.HTTP_200_OK, response_model=SummaryListResponse)
async def get_course_summaries(
    course_id: str,
    current_user=Depends(get_current_user),
    skip: int = 0,
    limit: int = 20
):
    """
    Get all summaries for a specific course
    """
    try:
        # Verify user has access to the course
        course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found."
            )

        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        }) is not None

        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied."
            )

        # Get summaries for this course
        summaries = []
        summary_cursor = db["summaries"].find({
            "course_id": ObjectId(course_id)
        }).skip(skip).limit(limit)

        async for summary in summary_cursor:
            summary_response = SummaryResponse(
                summaryId=str(summary["_id"]),
                videoId=str(summary.get("video_id")) if summary.get("video_id") else None,
                resourceId=str(summary.get("resource_id")) if summary.get("resource_id") else None,
                moduleId=str(summary.get("module_id")) if summary.get("module_id") else None,
                courseId=course_id,
                lengthType=summary["length_type"],
                content=summary["content"],
                wordCount=summary["word_count"],
                version=summary["version"],
                isPublished=summary.get("is_published", False),
                createdAt=summary["created_at"],
                updatedAt=summary.get("updated_at"),
                focusAreas=summary.get("focus_areas", [])
            )
            summaries.append(summary_response)

        total_count = await db["summaries"].count_documents({"course_id": ObjectId(course_id)})

        return SummaryListResponse(
            summaries=summaries,
            pagination={
                "total": total_count,
                "page": (skip // limit) + 1,
                "limit": limit,
                "hasNext": (skip + limit) < total_count,
                "hasPrev": skip > 0
            }
        )
    except Exception as e:
        logging.error(f"Error retrieving course summaries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve course summaries: {str(e)}"
        )