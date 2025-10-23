from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.course import CourseCreate, CourseCreateResponse, CourseJoinRequest, CourseJoinResponse, CourseListQuery, CourseListResponse
from bson import ObjectId
from datetime import datetime
import secrets
import string

router = APIRouter()

def generate_invitation_code():
    """Generate a random 8-character invitation code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

@router.post("/", response_model=CourseCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_course(course_data: CourseCreate, current_user=Depends(get_current_user)):
    # Only faculty can create courses
    if current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can create courses."
        )
    
    name = course_data.name.strip()
    description = course_data.description.strip()
    
    # Generate unique invitation code
    invitation_code = generate_invitation_code()
    while await db["course_rooms"].find_one({"invitation_code": invitation_code}):
        invitation_code = generate_invitation_code()
    
    course_doc = {
        "name": name,
        "description": description,
        "invitation_code": invitation_code,
        "created_by": ObjectId(current_user["_id"]),
        "status": "ACTIVE",
        "created_at": datetime.utcnow()
    }
    
    result = await db["course_rooms"].insert_one(course_doc)
    
    return CourseCreateResponse(
        courseId=str(result.inserted_id),
        name=name,
        description=description,
        invitationCode=invitation_code,
        invitationLink=f"https://eduassist.ai/join/{invitation_code}",
        createdAt=course_doc["created_at"],
        status="ACTIVE"
    )

@router.post("/join", response_model=CourseJoinResponse, status_code=status.HTTP_200_OK)
async def join_course(request_data: CourseJoinRequest, current_user=Depends(get_current_user)):
    # Faculty cannot join courses as students
    if current_user.get('role') == 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty users cannot join as students."
        )
    
    invitation_code = request_data.invitationCode
    
    # Find the course with the invitation code
    course = await db["course_rooms"].find_one({"invitation_code": invitation_code})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation code."
        )
    
    # Check if user is already enrolled
    existing_enrollment = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]),
        "course_id": course["_id"]
    })
    if existing_enrollment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already enrolled in course."
        )
    
    # Create enrollment
    enrollment_doc = {
        "user_id": ObjectId(current_user["_id"]),
        "course_id": course["_id"],
        "joined_at": datetime.utcnow()
    }
    
    result = await db["enrollments"].insert_one(enrollment_doc)
    
    return CourseJoinResponse(
        enrollmentId=str(result.inserted_id),
        courseId=str(course["_id"]),
        courseName=course["name"],
        role="STUDENT",  # Students join as students
        joinedAt=enrollment_doc["joined_at"]
    )

@router.get("/", response_model=CourseListResponse, status_code=status.HTTP_200_OK)
async def get_course_list(
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
    
    # Faculty can view courses they created; students can view enrolled courses
    query = {}
    if current_user.get('role') == 'FACULTY':
        # Faculty sees courses they created
        query = {"created_by": ObjectId(current_user["_id"])}
        if status_filter:
            query["status"] = status_filter
    else:
        # Students see courses they're enrolled in
        enrolled_courses = await db["enrollments"].find({
            "user_id": ObjectId(current_user["_id"])
        })
        course_ids = [enrollment["course_id"] async for enrollment in enrolled_courses]
        query = {"_id": {"$in": course_ids}}
        if status_filter:
            query["status"] = status_filter
    
    # Get total count for pagination
    total_count = await db["course_rooms"].count_documents(query)
    
    # Get paginated results
    courses = []
    async for course in db["course_rooms"].find(query).skip((page - 1) * limit).limit(limit):
        course_data = {
            "id": str(course["_id"]),
            "name": course["name"],
            "description": course["description"],
            "status": course["status"],
            "createdAt": course["created_at"],
            "createdBy": str(course["created_by"])
        }
        courses.append(course_data)
    
    return CourseListResponse(
        courses=courses,
        pagination={
            "currentPage": page,
            "totalPages": (total_count + limit - 1) // limit if limit > 0 else 1,
            "totalItems": total_count,
            "itemsPerPage": limit
        }
    )