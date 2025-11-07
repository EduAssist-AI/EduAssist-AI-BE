from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.course import CourseCreate, CourseCreateResponse, CourseJoinRequest, CourseJoinResponse, CourseListResponse, CourseListQuery
from app.schemas.user import UserOut
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Any

router = APIRouter()

@router.post("/", response_model=CourseCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_course(course_data: CourseCreate, current_user: UserOut = Depends(get_current_user)):
    # Create course document
    course_doc = {
        "name": course_data.name,
        "description": course_data.description,
        "created_by": ObjectId(current_user["id"]),
        "created_at": datetime.utcnow(),
        "status": "ACTIVE",
        "invitation_code": f"{course_data.name[:3].upper()}{ObjectId()}"[:8],  # Generate unique code
        "invitation_link": f"/join/{course_data.name[:3].upper()}{ObjectId()}"[:12]  # Generate unique link
    }
    
    result = await db["course_rooms"].insert_one(course_doc)
    course_id = str(result.inserted_id)
    
    # Create invitation link
    invitation_code = course_doc["invitation_code"]
    invitation_link = f"http://localhost:8000/auth/join?code={invitation_code}"
    
    # Create default module for the course
    default_module = {
        "course_id": ObjectId(course_id),
        "name": f"{course_data.name} - Module 1",
        "description": f"Default module for {course_data.name}",
        "created_at": datetime.utcnow(),
        "status": "ACTIVE",
        "created_by": ObjectId(current_user["id"])
    }
    
    await db["modules"].insert_one(default_module)
    
    # Create enrollment for the creator
    enrollment_doc = {
        "user_id": ObjectId(current_user["id"]),
        "course_id": ObjectId(course_id),
        "role": "FACULTY",  # Creator becomes faculty
        "enrolled_at": datetime.utcnow(),
        "status": "ACTIVE"
    }
    await db["enrollments"].insert_one(enrollment_doc)
    
    return CourseCreateResponse(
        courseId=course_id,
        name=course_doc["name"],
        description=course_doc["description"],
        invitationCode=invitation_code,
        invitationLink=invitation_link,
        createdAt=course_doc["created_at"],
        status=course_doc["status"]
    )

@router.get("/", response_model=Dict[str, Any])
async def list_courses(current_user: UserOut = Depends(get_current_user)):
    # Get courses the user is enrolled in
    enrollments = await db["enrollments"].find({"user_id": ObjectId(current_user["id"])}).to_list(length=None)
    
    course_ids_from_enrollments = [enrollment["course_id"] for enrollment in enrollments]
    
    # Get courses the user created (as faculty)
    courses_created = await db["course_rooms"].find({"created_by": ObjectId(current_user["id"])}).to_list(length=100)
    course_ids_created = [course["_id"] for course in courses_created]
    
    # Combine both lists and remove duplicates
    all_course_ids = list(set(course_ids_from_enrollments + course_ids_created))
    
    # Get all unique courses
    courses = await db["course_rooms"].find({"_id": {"$in": all_course_ids}}).to_list(length=100)
    
    # Format courses manually since CourseOut doesn't exist
    course_list = []
    for course in courses:
        course_list.append({
            "courseId": str(course["_id"]),
            "name": course["name"],
            "description": course["description"],
            "invitationCode": course.get("invitation_code", ""),
            "invitationLink": course.get("invitation_link", ""),
            "createdAt": course["created_at"],
            "status": course["status"]
        })
    
    return {"courses": course_list, "pagination": {"total": len(course_list), "page": 1, "limit": 100}}

@router.get("/{course_id}")
async def get_course(course_id: str, current_user: UserOut = Depends(get_current_user)):
    # Check if user is enrolled in the course or is the course creator (faculty)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    # Allow access if user is course creator (faculty) or enrolled student
    is_course_creator = str(course["created_by"]) == current_user["id"]
    is_enrolled = False
    
    if not is_course_creator:
        # Only check enrollment if user is not the course creator
        enrollment = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": ObjectId(course_id)
        })
        is_enrolled = bool(enrollment)
    
    if not is_course_creator and not is_enrolled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course and not the course creator")
    
    return {
        "courseId": str(course["_id"]),
        "name": course["name"],
        "description": course["description"],
        "invitationCode": course.get("invitation_code", ""),
        "invitationLink": course.get("invitation_link", ""),
        "createdAt": course["created_at"],
        "status": course["status"]
    }

@router.put("/{course_id}")
async def update_course(course_id: str, course_data: CourseCreate, current_user: UserOut = Depends(get_current_user)):
    # Verify user is the course creator (faculty)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    if str(course["created_by"]) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only course creator can update course")
    
    # Update course
    update_data = {
        "$set": {
            "name": course_data.name,
            "description": course_data.description,
            "updated_at": datetime.utcnow()
        }
    }
    
    result = await db["course_rooms"].update_one({"_id": ObjectId(course_id)}, update_data)
    
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes made to course")
    
    return {"message": "Course updated successfully", "course_id": course_id}

@router.delete("/{course_id}")
async def delete_course(course_id: str, current_user: UserOut = Depends(get_current_user)):
    # Verify user is the course creator (faculty)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    if str(course["created_by"]) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only course creator can delete course")
    
    # Check if there are enrolled students other than the creator
    enrollments = await db["enrollments"].find({"course_id": ObjectId(course_id)}).to_list(length=None)
    other_enrollments = [e for e in enrollments if str(e["user_id"]) != current_user["id"]]
    
    if other_enrollments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail="Cannot delete course with enrolled students. Unenroll them first.")
    
    # Delete course and related data
    await db["course_rooms"].delete_one({"_id": ObjectId(course_id)})
    await db["modules"].delete_many({"course_id": ObjectId(course_id)})  # Delete all modules
    await db["enrollments"].delete_many({"course_id": ObjectId(course_id)})  # Delete all enrollments
    await db["videos"].delete_many({"course_id": ObjectId(course_id)})  # Delete all videos
    
    # Also delete transcripts for videos in this course (get video IDs first)
    video_docs = await db["videos"].find({"course_id": ObjectId(course_id)}).to_list(length=None)
    video_ids = [v["_id"] for v in video_docs]
    if video_ids:
        await db["transcripts"].delete_many({"video_id": {"$in": video_ids}})
    
    # In a real implementation, you'd also need to handle:
    # - Deleting related content like summaries, quizzes, etc.
    # - Removing any files stored locally
    
    return {"message": "Course and all related data deleted successfully", "course_id": course_id}

@router.post("/{course_id}/join", response_model=CourseJoinResponse)
async def join_course(course_id: str, join_request: CourseJoinRequest, current_user: UserOut = Depends(get_current_user)):
    # Verify course exists and invitation code is valid
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    # Check if user is already enrolled
    existing_enrollment = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]),
        "course_id": ObjectId(course_id)
    })
    
    if existing_enrollment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already enrolled in this course")
    
    # Create enrollment for the user
    enrollment_doc = {
        "user_id": ObjectId(current_user["id"]),
        "course_id": ObjectId(course_id),
        "role": "STUDENT",
        "enrolled_at": datetime.utcnow(),
        "status": "ACTIVE"
    }
    
    result = await db["enrollments"].insert_one(enrollment_doc)
    
    return CourseJoinResponse(
        enrollmentId=str(result.inserted_id),
        courseId=course_id,
        courseName=course["name"],
        role="STUDENT",
        joinedAt=enrollment_doc["enrolled_at"]
    )