from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.video import ResourceUploadResponse, ResourceOut, ResourceListResponse
from app.schemas.user import UserOut
from app.schemas.course import CourseCreateResponse  # For course owner check
from app.utils.google_drive import upload_file_to_drive
from bson import ObjectId
from datetime import datetime
import os
import shutil

# Import for document processing
from app.utils.document_processor import DocumentProcessor
from app.utils.summary_generator import SummaryGenerator, SummaryRequest

router = APIRouter()

# Max file size for document upload (2GB)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

# Allowed document types
ALLOWED_DOCUMENT_TYPES = ["application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]

@router.post("/{courseId}/documents", response_model=ResourceUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    courseId: str,
    module_id: str = Form(None),  # Optional module ID for associating document with a specific module
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Upload a document (PDF, DOCX, TXT) to a course
    """
    # 1. Validate course existence and user permissions
    course_obj_id = ObjectId(courseId)
    course = await db["course_rooms"].find_one({"_id": course_obj_id})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")

    if current_user.get('role') != 'FACULTY' or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty who created the course can upload documents."
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
    if file.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported document format. Allowed types: PDF, DOCX, TXT."
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

    # 3. Handle storage based on the upload_to_drive flag
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload document to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type == "application/pdf":
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

    # 4. Determine document type and store metadata in MongoDB
    if file.content_type == "application/pdf":
        doc_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        doc_type = "docx"
    elif file.content_type == "text/plain":
        doc_type = "txt"
    else:
        doc_type = "unknown"

    # Check file extension as well to ensure consistency
    filename_lower = file.filename.lower()
    if filename_lower.endswith('.pdf'):
        doc_type = "pdf"
    elif filename_lower.endswith('.docx'):
        doc_type = "docx"
    elif filename_lower.endswith('.txt'):
        doc_type = "txt"

    document_doc = {
        "course_id": course_obj_id,
        "module_id": module_obj_id,  # Store module ID if provided
        "title": title,
        "type": doc_type,  # Store document type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING",  # Document processing happens immediately
        "published": False,
        "duration_seconds": 0,  # Documents don't have duration
        "uploaded_at": datetime.utcnow(),
        "processed_at": datetime.utcnow()  # Document processing happens immediately
    }
    result = await db["resources"].insert_one(document_doc)
    document_id = str(result.inserted_id)

    # 5. Process document and store content in transcript table
    try:
        doc_processor = DocumentProcessor()
        content = doc_processor.process_document(storage_url, doc_type)

        if content:
            # Save document content to transcript table using the updated method
            result = await doc_processor.save_document_content(content, document_id)
            print(f"Document {document_id} processed. {result}")
        else:
            print(f"Warning: Could not extract content from document {document_id}")
    except Exception as e:
        print(f"Error processing document {document_id}: {e}")

    # Update document status to COMPLETE
    await db["resources"].update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {
            "status": "COMPLETE",
            "processed_at": datetime.utcnow(),
            "duration_seconds": 0  # Documents don't have duration
        }}
    )

    return ResourceUploadResponse(
        resourceId=document_id,
        title=title,
        type=doc_type,
        status="COMPLETE",  # Since it's processed immediately
        statusUrl=f"/api/v1/documents/{document_id}/status",
        estimatedProcessingTime=0  # No additional processing time since it's done now
    )


@router.post("/{courseId}/documents-sync", response_model=ResourceUploadResponse, status_code=status.HTTP_200_OK)
async def upload_document_sync(
    courseId: str,
    module_id: str = Form(None),  # Optional module ID for associating document with a specific module
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Synchronous document upload and processing
    """
    # 1. Validate course existence and user permissions
    course_obj_id = ObjectId(courseId)
    course = await db["course_rooms"].find_one({"_id": course_obj_id})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")

    if current_user.get('role') != 'FACULTY' or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty who created the course can upload documents."
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
    if file.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported document format. Allowed types: PDF, DOCX, TXT."
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

    # 3. Handle storage based on the upload_to_drive flag
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload document to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type == "application/pdf":
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

    # 4. Determine document type and store metadata in MongoDB
    if file.content_type == "application/pdf":
        doc_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        doc_type = "docx"
    elif file.content_type == "text/plain":
        doc_type = "txt"
    else:
        doc_type = "unknown"

    # Check file extension as well to ensure consistency
    filename_lower = file.filename.lower()
    if filename_lower.endswith('.pdf'):
        doc_type = "pdf"
    elif filename_lower.endswith('.docx'):
        doc_type = "docx"
    elif filename_lower.endswith('.txt'):
        doc_type = "txt"

    document_doc = {
        "course_id": course_obj_id,
        "module_id": module_obj_id,  # Store module ID if provided
        "title": title,
        "type": doc_type,  # Store document type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING",  # Start as processing since we're doing it now
        "published": False,
        "duration_seconds": 0,  # Documents don't have duration
        "uploaded_at": datetime.utcnow(),
        "processed_at": None
    }
    result = await db["resources"].insert_one(document_doc)
    document_id = str(result.inserted_id)

    # 5. Process the document
    try:
        doc_processor = DocumentProcessor()
        content = doc_processor.process_document(storage_url, doc_type)

        if content:
            # Save document content to database
            await doc_processor.save_document_content(content, document_id)
            print(f"Document {document_id} processed and content saved.")
        else:
            print(f"Warning: Could not extract content from document {document_id}")

        # Update document status to COMPLETE
        await db["resources"].update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": "COMPLETE", "processed_at": datetime.utcnow()}}
        )
    except Exception as e:
        import logging
        logging.error(f"Error processing document {document_id} synchronously: {e}")

        # Update document status to FAILED
        try:
            await db["resources"].update_one(
                {"_id": ObjectId(document_id)},
                {"$set": {"status": "FAILED", "error_message": str(e)}}
            )
        except:
            pass  # Ignore errors in error handling

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Document processing failed: {str(e)}")

    print(f"Document {document_id} uploaded and processed synchronously.")

    return ResourceUploadResponse(
        resourceId=document_id,
        title=title,
        type=doc_type,
        status="COMPLETE",  # Since it's processed synchronously
        statusUrl=f"/api/v1/documents/{document_id}/status",
        estimatedProcessingTime=0  # No additional processing time since it's done now
    )


# New module-specific endpoints for documents
@router.post("/modules/{moduleId}/documents-sync", response_model=ResourceUploadResponse, status_code=status.HTTP_200_OK)
async def upload_document_sync_to_module(
    moduleId: str,
    title: str = Form(...),
    upload_to_drive: bool = Form(True),  # Whether to upload to Google Drive (default: True)
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Synchronous document upload to a specific module
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
            detail="Only faculty who created the course can upload documents to modules."
        )

    # 2. Validate file size and type
    if file.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported document format. Allowed types: PDF, DOCX, TXT."
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

    # 3. Handle storage based on the upload_to_drive flag
    if upload_to_drive:
        # Upload to Google Drive
        google_drive_file_id = await upload_file_to_drive(temp_file_path, file.filename, file.content_type)

        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if not google_drive_file_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload document to Google Drive.")

        storage_url = google_drive_file_id
        storage_type = "drive"
    else:
        # Store file locally in uploads folder
        import uuid
        from pathlib import Path

        # Determine upload directory based on file type
        if file.content_type == "application/pdf":
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

    # 4. Determine document type and store metadata in MongoDB
    if file.content_type == "application/pdf":
        doc_type = "pdf"
    elif file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        doc_type = "docx"
    elif file.content_type == "text/plain":
        doc_type = "txt"
    else:
        doc_type = "unknown"

    # Check file extension as well to ensure consistency
    filename_lower = file.filename.lower()
    if filename_lower.endswith('.pdf'):
        doc_type = "pdf"
    elif filename_lower.endswith('.docx'):
        doc_type = "docx"
    elif filename_lower.endswith('.txt'):
        doc_type = "txt"

    document_doc = {
        "course_id": module["course_id"],
        "module_id": module_obj_id,  # Store the module ID
        "title": title,
        "type": doc_type,  # Store document type
        "storage_url": storage_url,  # This will be the Google Drive File ID or local file path
        "storage_type": storage_type,  # Store the storage type ("drive" or "local")
        "status": "PROCESSING",  # Start as processing since we're doing it now
        "published": False,
        "duration_seconds": 0,  # Documents don't have duration
        "uploaded_at": datetime.utcnow(),
        "processed_at": None
    }
    result = await db["resources"].insert_one(document_doc)
    document_id = str(result.inserted_id)

    # 5. Process the document
    try:
        doc_processor = DocumentProcessor()
        content = doc_processor.process_document(storage_url, doc_type)

        if content:
            # Save document content to database
            await doc_processor.save_document_content(content, document_id)
            print(f"Document {document_id} processed and content saved.")
        else:
            print(f"Warning: Could not extract content from document {document_id}")

        # Update document status to COMPLETE
        await db["resources"].update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": "COMPLETE", "processed_at": datetime.utcnow()}}
        )
    except Exception as e:
        import logging
        logging.error(f"Error processing document {document_id} synchronously: {e}")

        # Update document status to FAILED
        try:
            await db["resources"].update_one(
                {"_id": ObjectId(document_id)},
                {"$set": {"status": "FAILED", "error_message": str(e)}}
            )
        except:
            pass  # Ignore errors in error handling

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Document processing failed: {str(e)}")

    print(f"Document {document_id} uploaded and processed synchronously to module {moduleId}.")

    return ResourceUploadResponse(
        resourceId=document_id,
        title=title,
        type=doc_type,
        status="COMPLETE",  # Since it's processed synchronously
        statusUrl=f"/api/v1/documents/{document_id}/status",
        estimatedProcessingTime=0  # No additional processing time since it's done now
    )


@router.get("/modules/{moduleId}/documents", response_model=ResourceListResponse)
async def list_documents_by_module(
    moduleId: str,
    current_user: UserOut = Depends(get_current_user)
):
    """
    List all documents associated with a specific module
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

    # Find all documents associated with this module (filter by type)
    documents = await db["resources"].find({
        "module_id": module_obj_id,
        "type": {"$in": ["pdf", "docx", "txt"]}  # Only documents
    }).to_list(length=100)

    # Convert to ResourceOut format
    document_list = []
    for document in documents:
        document_out = ResourceOut(
            id=str(document["_id"]),
            title=document["title"],
            type=document.get("type", "unknown"),
            durationSeconds=document.get("duration_seconds"),
            status=document["status"],
            published=document.get("published", False),
            publishedAt=document.get("published_at"),
            thumbnailUrl=document.get("thumbnail_url"),
            hasTranscript=await db["transcripts"].find_one({"resource_id": ObjectId(document["_id"])}) is not None,
            hasSummary=await db["summaries"].find_one({"resource_id": ObjectId(document["_id"])}) is not None,
            hasQuiz=await db["quizzes"].find_one({"resource_id": ObjectId(document["_id"])}) is not None
        )
        document_list.append(document_out)

    return ResourceListResponse(
        resources=document_list,
        pagination={
            "total": len(document_list),
            "page": 1,
            "limit": 100
        }
    )


@router.post("/documents/{document_id}/summaries", status_code=status.HTTP_201_CREATED)
async def generate_document_summary(
    document_id: str,
    request_data: SummaryRequest,
    current_user=Depends(get_current_user)
):
    """
    Generate a summary for a specific document
    """
    # Find the document
    document = await db["resources"].find_one({"_id": ObjectId(document_id)})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )

    # Check if user has access (course owner or enrolled student)
    course = await db["course_rooms"].find_one({"_id": document["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document course not found."
        )

    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": document["course_id"]
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

    # Get the transcript for this document
    transcript = await db["transcripts"].find_one({"resource_id": ObjectId(document_id)})
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No transcript found for this document."
        )

    # Convert transcript segments to the required format (same as for videos)
    from app.rag.generator import TranscriptSegment
    transcript_segments = [
        TranscriptSegment(start=seg["start"], end=seg["end"], text=seg["text"])
        for seg in transcript["segments"]
    ]

    # Initialize summary generator and create summary
    summary_generator = SummaryGenerator()
    summary_response = await summary_generator.generate_and_store_document_summary(
        document_id,
        transcript_segments,
        length_type,
        request_data.focus_areas
    )

    return {
        "summaryId": summary_response.summaryId,
        "documentId": document_id,
        "lengthType": summary_response.lengthType,
        "content": summary_response.content,
        "wordCount": summary_response.wordCount,
        "version": summary_response.version,
        "isPublished": summary_response.isPublished,
        "createdAt": datetime.utcnow()
    }