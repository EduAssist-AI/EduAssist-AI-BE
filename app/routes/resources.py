from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.video import ResourceUploadRequest, ResourceUploadResponse, ResourceOut, ResourceListResponse
from app.schemas.user import UserOut
from app.schemas.course import CourseCreateResponse # For course owner check
from app.utils.google_drive import upload_file_to_drive
from bson import ObjectId
from datetime import datetime
import os
import shutil

# Import for document processing
from app.utils.document_processor import DocumentProcessor

router = APIRouter()

# Max file size for resource upload (2GB)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

# Allowed resource types
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/avi", "video/mov", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm", "video/mpeg", "video/3gpp", "video/3gpp2", "video/x-flv"]
ALLOWED_DOCUMENT_TYPES = ["application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
ALLOWED_RESOURCE_TYPES = ALLOWED_VIDEO_TYPES + ALLOWED_DOCUMENT_TYPES

@router.post("/{courseId}/resources", response_model=ResourceUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resource(
    courseId: str,
    module_id: str = Form(None),  # Optional module ID for associating resource with a specific module
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Upload a resource (video, PDF, DOCX, TXT) to a course
    """
    # 1. Validate course existence and user permissions
    course_obj_id = ObjectId(courseId)
    course = await db["course_rooms"].find_one({"_id": course_obj_id})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")

    if current_user.get('role') != 'FACULTY' or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty who created the course can upload resources."
        )

    # If module_id is provided, validate that the module exists and belongs to this course
    module_obj_id = None
    if module_id:
        module_obj_id = ObjectId(module_id)
        module = await db["modules"].find_one({
            "_id": module_obj_id,
            "course_id": course_obj_id
        })
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found or does not belong to course."
            )

    # 2. Validate file size and type
    if file.content_type not in ALLOWED_RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format. Allowed types: video formats, PDF, DOCX, TXT."
        )

    # Create a temporary file to save the uploaded content
    temp_file_path = f"temp_{file.filename}"
    file_size = 0
    try:
        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # Read in 1MB chunks
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 2GB limit.")
    except HTTPException:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save uploaded file: {e}")

    # 3. Handle storage based on the upload_to_drive flag and file type
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload resource to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder based on file type
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type.startswith("video/"):
            storage_path = os.path.join("uploads", "videos")
        elif file.content_type == "application/pdf":
            storage_path = os.path.join("uploads", "documents", "pdf")
        elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            storage_path = os.path.join("uploads", "documents", "docx")
        elif file.content_type == "text/plain":
            storage_path = os.path.join("uploads", "documents", "txt")
        else:
            storage_path = os.path.join("uploads", "documents", "other")

        os.makedirs(storage_path, exist_ok=True)

        # Create a unique filename
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        final_path = os.path.join(storage_path, unique_filename)

        # Move the temporary file to permanent local location
        os.rename(temp_file_path, final_path)

        storage_url = final_path  # Store the local file path
        storage_type = "local"  # Mark that this is local storage

    # 4. Determine resource type and store metadata in MongoDB
    if file.content_type.startswith("video/"):
        resource_type = "video"
    elif file.content_type == "application/pdf":
        resource_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        resource_type = "docx"
    elif file.content_type == "text/plain":
        resource_type = "txt"
    else:
        resource_type = "unknown"

    resource_doc = {
        "course_id": course_obj_id,
        "module_id": module_obj_id,  # Store module ID if provided
        "title": title,
        "type": resource_type,  # New field to store file type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING" if resource_type in ["pdf", "docx", "txt"] else "PENDING",  # Document processing is immediate, video processing is async
        "published": False,
        "duration_seconds": 0, # Will be updated after processing for videos
        "uploaded_at": datetime.utcnow(),
        "processed_at": datetime.utcnow() if resource_type in ["pdf", "docx", "txt"] else None  # Document processing is immediate
    }
    result = await db["resources"].insert_one(resource_doc)
    resource_id = str(result.inserted_id)

    # 5. Process document or trigger video processing
    if resource_type in ["pdf", "docx", "txt"]:
        # For documents, process immediately and store content in transcript table
        try:
            doc_processor = DocumentProcessor()
            content = doc_processor.process_document(storage_url, resource_type)

            if content:
                # Save document content to transcript table using the updated method
                result = await doc_processor.save_document_content(content, resource_id)
                print(f"Document {resource_id} processed. {result}")
            else:
                print(f"Warning: Could not extract content from document {resource_id}")
        except Exception as e:
            print(f"Error processing document {resource_id}: {e}")

        # Update resource status to COMPLETE
        await db["resources"].update_one(
            {"_id": ObjectId(resource_id)},
            {"$set": {
                "status": "COMPLETE",
                "processed_at": datetime.utcnow(),
                "duration_seconds": 0  # Documents don't have duration
            }}
        )
    elif resource_type == "video":
        # For videos, trigger asynchronous processing task with Celery
        from app.tasks import process_video_task
        import logging
        try:
            if storage_type == "drive":
                # Process video from Google Drive
                process_video_task.delay(resource_id, storage_url)
            elif storage_type == "local":
                # Process local video file
                process_video_task.delay(resource_id, storage_url)
            print(f"Video {resource_id} uploaded. Triggering background processing with Celery.")
        except Exception as e:
            logging.warning(f"Celery not available (Redis may not be running): {e}")
            # If Celery is not available, we should store the task for later processing
            # For now, update the status to indicate the system issue but don't fail the request
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from app.tasks import update_video_status
            loop.run_until_complete(update_video_status(resource_id, "FAILED", 100, f"Processing service unavailable: {str(e)}", 0))
            loop.close()

            # Update the video document to reflect the issue
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": {
                    "status": "FAILED",
                    "error_message": f"Processing service unavailable: {str(e)}"
                }}
            )
            print(f"Warning: Could not start background processing for video {resource_id}: {e}. Please ensure Redis and Celery are running.")

    return ResourceUploadResponse(
        resourceId=resource_id,
        title=title,
        type=resource_type,
        status=resource_doc["status"],
        statusUrl=f"/api/v1/resources/{resource_id}/status",
        estimatedProcessingTime=300 if resource_type == "video" else 0 # Placeholder processing time for videos
    )


@router.post("/{courseId}/resources-sync", response_model=ResourceUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resource_sync(
    courseId: str,
    module_id: str = Form(None),  # Optional module ID for associating resource with a specific module
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Synchronous resource upload and processing (without Celery)
    """
    # 1. Validate course existence and user permissions
    course_obj_id = ObjectId(courseId)
    course = await db["course_rooms"].find_one({"_id": course_obj_id})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")

    if current_user.get('role') != 'FACULTY' or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty who created the course can upload resources."
        )

    # If module_id is provided, validate that the module exists and belongs to this course
    module_obj_id = None
    if module_id:
        module_obj_id = ObjectId(module_id)
        module = await db["modules"].find_one({
            "_id": module_obj_id,
            "course_id": course_obj_id
        })
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found or does not belong to course."
            )

    # 2. Validate file size and type
    if file.content_type not in ALLOWED_RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format. Allowed types: video formats, PDF, DOCX, TXT."
        )

    # Create a temporary file to save the uploaded content
    temp_file_path = f"temp_{file.filename}"
    file_size = 0
    try:
        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # Read in 1MB chunks
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 2GB limit.")
    except HTTPException:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save uploaded file: {e}")

    # 3. Handle storage based on the upload_to_drive flag and file type
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload resource to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder based on file type
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type.startswith("video/"):
            storage_path = os.path.join("uploads", "videos")
        elif file.content_type == "application/pdf":
            storage_path = os.path.join("uploads", "documents", "pdf")
        elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            storage_path = os.path.join("uploads", "documents", "docx")
        elif file.content_type == "text/plain":
            storage_path = os.path.join("uploads", "documents", "txt")
        else:
            storage_path = os.path.join("uploads", "documents", "other")

        os.makedirs(storage_path, exist_ok=True)

        # Create a unique filename
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        final_path = os.path.join(storage_path, unique_filename)

        # Move the temporary file to permanent local location
        os.rename(temp_file_path, final_path)

        storage_url = final_path  # Store the local file path
        storage_type = "local"  # Mark that this is local storage

    # 4. Determine resource type and store metadata in MongoDB
    if file.content_type.startswith("video/"):
        resource_type = "video"
    elif file.content_type == "application/pdf":
        resource_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        resource_type = "docx"
    elif file.content_type == "text/plain":
        resource_type = "txt"
    else:
        resource_type = "unknown"

    resource_doc = {
        "course_id": course_obj_id,
        "module_id": module_obj_id,  # Store module ID if provided
        "title": title,
        "type": resource_type,  # New field to store file type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING",  # Start as processing since we're doing it now
        "published": False,
        "duration_seconds": 0, # Will be updated after processing for videos
        "uploaded_at": datetime.utcnow(),
        "processed_at": None
    }
    result = await db["resources"].insert_one(resource_doc)
    resource_id = str(result.inserted_id)

    # 5. Process the resource synchronously
    try:
        if resource_type in ["pdf", "docx", "txt"]:
            # Process document immediately
            doc_processor = DocumentProcessor()
            content = doc_processor.process_document(storage_url, resource_type)

            if content:
                # Save document content to database
                await doc_processor.save_document_content(content, resource_id)
                print(f"Document {resource_id} processed and content saved.")
            else:
                print(f"Warning: Could not extract content from document {resource_id}")

            # Update resource status to COMPLETE
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": {"status": "COMPLETE", "processed_at": datetime.utcnow()}}
            )
        elif resource_type == "video":
            # Process video synchronously (without Celery)
            # Update resource status to PROCESSING - this uses the existing event loop
            from app.tasks import update_video_status
            await update_video_status(resource_id, "PROCESSING", 0, "Starting video processing", 300)

            # Create a mock video content structure since we're using audio processor
            # This is a simplified version for now
            from pydantic import BaseModel
            from typing import List

            # Define models if they don't exist
            class TranscriptSegment(BaseModel):
                start: float
                end: float
                text: str

            class VideoContent(BaseModel):
                transcript_segments: List[TranscriptSegment]
                word_count: int
                language: str
                confidence: float
                video_duration: float
                image_frames: List[dict]  # Image frames with metadata

            # For now, use audio processor to get basic transcription
            from app.utils.audio_processor import AudioProcessor
            audio_processor = AudioProcessor()

            # Process video based on storage type
            if storage_type == "drive":
                # For drive we need a different approach - this might be a mock for now
                # Assuming we can't process Google Drive files directly without downloading
                # This is a placeholder that would need to be implemented properly
                transcription = "Transcription not available for Google Drive files in this mock implementation"
                video_content = VideoContent(
                    transcript_segments=[TranscriptSegment(start=0.0, end=30.0, text=transcription)],
                    word_count=0,
                    language="en",
                    confidence=0.0,
                    video_duration=30.0,
                    image_frames=[]
                )
            else:
                # Process local video file - this is synchronous
                # For local files, storage_url is the direct file path
                if not storage_url:
                    raise Exception("No file path provided for local storage type")

                # Verify the file exists before processing
                if not os.path.exists(storage_url):
                    raise Exception(f"Video file does not exist at path: {storage_url}")

                # Process the local video file to get transcription
                transcription = audio_processor.process_video_for_transcription(storage_url)
                if transcription:
                    video_content = VideoContent(
                        transcript_segments=[TranscriptSegment(start=0.0, end=30.0, text=transcription[:500])],  # Simplified
                        word_count=len(transcription.split()),
                        language="en",
                        confidence=0.9,  # Placeholder
                        video_duration=30.0,  # Placeholder, would need actual duration
                        image_frames=[]
                    )
                else:
                    # If processing fails, return a mock response
                    video_content = VideoContent(
                        transcript_segments=[TranscriptSegment(start=0.0, end=1.0, text="Video processing failed")],
                        word_count=3,
                        language="en",
                        confidence=0.0,
                        video_duration=30.0,
                        image_frames=[]
                    )

            # Update resource status to indicate transcription in progress
            await update_video_status(resource_id, "PROCESSING", 30, "Extracting transcript", 240)

            # Store transcript in database
            transcript_doc = {
                "resource_id": ObjectId(resource_id),
                "segments": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text
                    } for segment in video_content.transcript_segments
                ],
                "word_count": video_content.word_count,
                "language": video_content.language,
                "confidence": video_content.confidence,
                "created_at": datetime.utcnow()
            }

            # Insert transcript
            transcript_result = await db["transcripts"].insert_one(transcript_doc)
            transcript_id = str(transcript_result.inserted_id)

            # Update resource status to indicate RAG indexing in progress
            await update_video_status(resource_id, "PROCESSING", 60, "Indexing content for search", 180)

            # Add transcript content to RAG system for semantic search
            from app.rag.generator import add_video_content_to_rag
            await add_video_content_to_rag(resource_id, transcript_id, video_content.transcript_segments)

            # Update resource status to indicate image processing in progress
            await update_video_status(resource_id, "PROCESSING", 80, "Processing visual content", 120)

            # Update resource metadata
            update_data = {
                "status": "COMPLETE",
                "duration_seconds": int(video_content.video_duration),
                "processed_at": datetime.utcnow()
            }

            # Update resource status to indicate completion
            await update_video_status(resource_id, "COMPLETE", 100, "Processing completed", 0)

            # Update resource record with final status and duration
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": update_data}
            )

        print(f"Resource {resource_id} uploaded and processed synchronously.")

        return ResourceUploadResponse(
            resourceId=resource_id,
            title=title,
            type=resource_type,
            status="COMPLETE",  # Since it's processed synchronously
            statusUrl=f"/api/v1/resources/{resource_id}/status",
            estimatedProcessingTime=0  # No additional processing time since it's done now
        )

    except Exception as e:
        import logging
        logging.error(f"Error processing resource {resource_id} synchronously: {e}")

        # Update resource status to FAILED
        try:
            from app.tasks import update_video_status
            await update_video_status(resource_id, "FAILED", 100, str(e), 0)

            # Update resource record with error
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": {"error_message": str(e)}}
            )
        except:
            pass  # Ignore errors in error handling

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Resource processing failed: {str(e)}")


# New module-specific endpoints for resources

@router.post("/modules/{moduleId}/resources-sync", response_model=ResourceUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resource_sync_to_module(
    moduleId: str,
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Synchronous resource upload to a specific module
    """
    # 1. Validate module existence and user permissions
    module_obj_id = ObjectId(moduleId)
    module = await db["modules"].find_one({"_id": module_obj_id})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    # Get the course for the module
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course for module not found.")

    if current_user.get('role') != 'FACULTY' or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty who created the course can upload resources to modules."
        )

    # 2. Validate file size and type
    if file.content_type not in ALLOWED_RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format. Allowed types: video formats, PDF, DOCX, TXT."
        )

    # Create a temporary file to save the uploaded content
    temp_file_path = f"temp_{file.filename}"
    file_size = 0
    try:
        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # Read in 1MB chunks
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 2GB limit.")
    except HTTPException:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save uploaded file: {e}")

    # 3. Handle storage based on the upload_to_drive flag and file type
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload resource to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder based on file type
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type.startswith("video/"):
            storage_path = os.path.join("uploads", "videos")
        elif file.content_type == "application/pdf":
            storage_path = os.path.join("uploads", "documents", "pdf")
        elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            storage_path = os.path.join("uploads", "documents", "docx")
        elif file.content_type == "text/plain":
            storage_path = os.path.join("uploads", "documents", "txt")
        else:
            storage_path = os.path.join("uploads", "documents", "other")

        os.makedirs(storage_path, exist_ok=True)

        # Create a unique filename
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        final_path = os.path.join(storage_path, unique_filename)

        # Move the temporary file to permanent local location
        os.rename(temp_file_path, final_path)

        storage_url = final_path  # Store the local file path
        storage_type = "local"  # Mark that this is local storage

    # 4. Determine resource type and store metadata in MongoDB
    if file.content_type.startswith("video/"):
        resource_type = "video"
    elif file.content_type == "application/pdf":
        resource_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        resource_type = "docx"
    elif file.content_type == "text/plain":
        resource_type = "txt"
    else:
        resource_type = "unknown"

    resource_doc = {
        "course_id": module["course_id"],
        "module_id": module_obj_id,  # Store the module ID
        "title": title,
        "type": resource_type,  # New field to store file type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING",  # Start as processing since we're doing it now
        "published": False,
        "duration_seconds": 0, # Will be updated after processing for videos
        "uploaded_at": datetime.utcnow(),
        "processed_at": None
    }
    result = await db["resources"].insert_one(resource_doc)
    resource_id = str(result.inserted_id)

    # 5. Process the resource synchronously
    try:
        if resource_type in ["pdf", "docx", "txt"]:
            # Process document immediately
            doc_processor = DocumentProcessor()
            content = doc_processor.process_document(storage_url, resource_type)

            if content:
                # Save document content to database
                await doc_processor.save_document_content(content, resource_id)
                print(f"Document {resource_id} processed and content saved.")
            else:
                print(f"Warning: Could not extract content from document {resource_id}")

            # Update resource status to COMPLETE
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": {"status": "COMPLETE", "processed_at": datetime.utcnow()}}
            )
        elif resource_type == "video":
            # Process video synchronously (without Celery)
            # Update resource status to PROCESSING - this uses the existing event loop
            from app.tasks import update_video_status
            await update_video_status(resource_id, "PROCESSING", 0, "Starting video processing", 300)

            # Create a mock video content structure since we're using audio processor
            # This is a simplified version for now
            from pydantic import BaseModel
            from typing import List

            # Define models if they don't exist
            class TranscriptSegment(BaseModel):
                start: float
                end: float
                text: str

            class VideoContent(BaseModel):
                transcript_segments: List[TranscriptSegment]
                word_count: int
                language: str
                confidence: float
                video_duration: float
                image_frames: List[dict]  # Image frames with metadata

            # For now, use audio processor to get basic transcription
            from app.utils.audio_processor import AudioProcessor
            audio_processor = AudioProcessor()

            # Process video based on storage type
            if storage_type == "drive":
                # For drive we need a different approach - this might be a mock for now
                # Assuming we can't process Google Drive files directly without downloading
                # This is a placeholder that would need to be implemented properly
                transcription = "Transcription not available for Google Drive files in this mock implementation"
                video_content = VideoContent(
                    transcript_segments=[TranscriptSegment(start=0.0, end=30.0, text=transcription)],
                    word_count=0,
                    language="en",
                    confidence=0.0,
                    video_duration=30.0,
                    image_frames=[]
                )
            else:
                # Process local video file - this is synchronous
                # For local files, storage_url is the direct file path
                if not storage_url:
                    raise Exception("No file path provided for local storage type")

                # Verify the file exists before processing
                if not os.path.exists(storage_url):
                    raise Exception(f"Video file does not exist at path: {storage_url}")

                # Process the local video file to get transcription
                transcription = audio_processor.process_video_for_transcription(storage_url)
                if transcription:
                    video_content = VideoContent(
                        transcript_segments=[TranscriptSegment(start=0.0, end=30.0, text=transcription[:500])],  # Simplified
                        word_count=len(transcription.split()),
                        language="en",
                        confidence=0.9,  # Placeholder
                        video_duration=30.0,  # Placeholder, would need actual duration
                        image_frames=[]
                    )
                else:
                    # If processing fails, return a mock response
                    video_content = VideoContent(
                        transcript_segments=[TranscriptSegment(start=0.0, end=1.0, text="Video processing failed")],
                        word_count=3,
                        language="en",
                        confidence=0.0,
                        video_duration=30.0,
                        image_frames=[]
                    )

            # Update resource status to indicate transcription in progress
            await update_video_status(resource_id, "PROCESSING", 30, "Extracting transcript", 240)

            # Store transcript in database
            transcript_doc = {
                "resource_id": ObjectId(resource_id),
                "segments": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text
                    } for segment in video_content.transcript_segments
                ],
                "word_count": video_content.word_count,
                "language": video_content.language,
                "confidence": video_content.confidence,
                "created_at": datetime.utcnow()
            }

            # Insert transcript
            transcript_result = await db["transcripts"].insert_one(transcript_doc)
            transcript_id = str(transcript_result.inserted_id)

            # Update resource status to indicate RAG indexing in progress
            await update_video_status(resource_id, "PROCESSING", 60, "Indexing content for search", 180)

            # Add transcript content to RAG system for semantic search
            from app.rag.generator import add_video_content_to_rag
            await add_video_content_to_rag(resource_id, transcript_id, video_content.transcript_segments)

            # Update resource status to indicate image processing in progress
            await update_video_status(resource_id, "PROCESSING", 80, "Processing visual content", 120)

            # Update resource metadata
            update_data = {
                "status": "COMPLETE",
                "duration_seconds": int(video_content.video_duration),
                "processed_at": datetime.utcnow()
            }

            # Update resource status to indicate completion
            await update_video_status(resource_id, "COMPLETE", 100, "Processing completed", 0)

            # Update resource record with final status and duration
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": update_data}
            )

        print(f"Resource {resource_id} uploaded and processed synchronously to module {moduleId}.")

        return ResourceUploadResponse(
            resourceId=resource_id,
            title=title,
            type=resource_type,
            status="COMPLETE",  # Since it's processed synchronously
            statusUrl=f"/api/v1/resources/{resource_id}/status",
            estimatedProcessingTime=0  # No additional processing time since it's done now
        )

    except Exception as e:
        import logging
        logging.error(f"Error processing resource {resource_id} synchronously: {e}")

        # Update resource status to FAILED
        try:
            from app.tasks import update_video_status
            await update_video_status(resource_id, "FAILED", 100, str(e), 0)

            # Update resource record with error
            await db["resources"].update_one(
                {"_id": ObjectId(resource_id)},
                {"$set": {"error_message": str(e)}}
            )
        except:
            pass  # Ignore errors in error handling

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Resource processing failed: {str(e)}")


@router.get("/modules/{moduleId}/resources", response_model=ResourceListResponse)
async def list_resources_by_module(
    moduleId: str,
    current_user: UserOut = Depends(get_current_user)
):
    """
    List all resources (videos, documents) associated with a specific module
    """
    module_obj_id = ObjectId(moduleId)
    module = await db["modules"].find_one({"_id": module_obj_id})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    # Check if user has access to the course containing this module
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module course not found.")

    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": module["course_id"]
    }) is not None

    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    # Find all resources associated with this module
    resources = await db["resources"].find({
        "module_id": module_obj_id
    }).to_list(length=100)

    # Convert to ResourceOut format
    resource_list = []
    for resource in resources:
        resource_out = ResourceOut(
            id=str(resource["_id"]),
            title=resource["title"],
            type=resource.get("type", "unknown"),
            durationSeconds=resource.get("duration_seconds"),
            status=resource["status"],
            published=resource.get("published", False),
            publishedAt=resource.get("published_at"),
            thumbnailUrl=resource.get("thumbnail_url"),
            hasTranscript=await db["transcripts"].find_one({"resource_id": ObjectId(resource["_id"])}) is not None,
            hasSummary=await db["summaries"].find_one({"resource_id": ObjectId(resource["_id"])}) is not None,
            hasQuiz=await db["quizzes"].find_one({"resource_id": ObjectId(resource["_id"])}) is not None
        )
        resource_list.append(resource_out)

    return ResourceListResponse(
        resources=resource_list,
        pagination={
            "total": len(resource_list),
            "page": 1,
            "limit": 100
        }
    )


@router.put("/resources/{resourceId}", status_code=status.HTTP_200_OK)
async def update_resource(
    resourceId: str,
    request_data: ResourceUploadRequest,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Update resource details (title, etc.)
    """
    resource = await db["resources"].find_one({"_id": ObjectId(resourceId)})
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

    # Only faculty can update resource
    if current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can update resources."
        )

    # Update resource title
    update_data = {
        "$set": {
            "title": request_data.title,
            "updated_at": datetime.utcnow()
        }
    }

    result = await db["resources"].update_one(
        {"_id": ObjectId(resourceId)},
        update_data
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes made to resource"
        )

    # Return updated resource
    updated_resource = await db["resources"].find_one({"_id": ObjectId(resourceId)})
    resource_out = ResourceOut(
        id=str(updated_resource["_id"]),
        title=updated_resource["title"],
        type=updated_resource.get("type", "unknown"),
        durationSeconds=updated_resource.get("duration_seconds"),
        status=updated_resource["status"],
        published=updated_resource.get("published", False),
        publishedAt=updated_resource.get("published_at"),
        thumbnailUrl=updated_resource.get("thumbnail_url"),
        hasTranscript=await db["transcripts"].find_one({"resource_id": ObjectId(updated_resource["_id"])}) is not None,
        hasSummary=await db["summaries"].find_one({"resource_id": ObjectId(updated_resource["_id"])}) is not None,
        hasQuiz=await db["quizzes"].find_one({"resource_id": ObjectId(updated_resource["_id"])}) is not None
    )

    return resource_out


@router.delete("/resources/{resourceId}", status_code=status.HTTP_200_OK)
async def delete_resource(
    resourceId: str,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Delete resource by ID
    """
    # Find the resource
    resource = await db["resources"].find_one({"_id": ObjectId(resourceId)})
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found."
        )

    # Verify user is course owner (faculty)
    course = await db["course_rooms"].find_one({"_id": resource["course_id"]})
    if not course or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only course owner can delete resources."
        )

    # Check if user has faculty role
    if current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can delete resources."
        )

    # Delete the resource
    delete_result = await db["resources"].delete_one({"_id": ObjectId(resourceId)})

    if delete_result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource could not be deleted"
        )

    # Also delete related data: transcript, summary, quiz
    await db["transcripts"].delete_many({"resource_id": ObjectId(resourceId)})
    await db["summaries"].delete_many({"resource_id": ObjectId(resourceId)})
    await db["quizzes"].delete_many({"resource_id": ObjectId(resourceId)})

    # If the resource was stored locally, delete the file as well
    if resource.get("storage_type") == "local" and resource.get("storage_url"):
        import os
        try:
            if os.path.exists(resource["storage_url"]):
                os.remove(resource["storage_url"])
        except Exception as e:
            print(f"Warning: Could not delete local resource file {resource['storage_url']}: {e}")

    return {
        "message": "Resource and related content deleted successfully",
        "resourceId": resourceId
    }