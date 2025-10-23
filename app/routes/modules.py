from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.modules import ModuleCreate, ModuleResponse, ModuleListResponse
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/courses/{course_id}/modules", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(course_id: str, module_data: ModuleCreate, current_user=Depends(get_current_user)):
    # Check if the user is the course owner (faculty)
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found."
        )
    
    if str(course["created_by"]) != current_user["_id"] or current_user.get('role') != 'FACULTY':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty members can create modules in this course."
        )
    
    name = module_data.name.strip()
    description = module_data.description.strip()
    
    module_doc = {
        "course_id": ObjectId(course_id),
        "name": name,
        "description": description,
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow(),
        "status": "ACTIVE"
    }
    
    result = await db["modules"].insert_one(module_doc)
    
    return ModuleResponse(
        moduleId=str(result.inserted_id),
        courseId=course_id,
        name=name,
        description=description,
        createdAt=module_doc["created_at"],
        status="ACTIVE"
    )

@router.get("/courses/{course_id}/modules", response_model=ModuleListResponse, status_code=status.HTTP_200_OK)
async def get_module_list(course_id: str, current_user=Depends(get_current_user)):
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
    
    # Get all modules for the course
    modules = []
    async for module in db["modules"].find({"course_id": ObjectId(course_id)}):
        module_response = {
            "moduleId": str(module["_id"]),
            "courseId": str(module["course_id"]),
            "name": module["name"],
            "description": module["description"],
            "createdAt": module["created_at"],
            "status": module["status"]
        }
        modules.append(module_response)
    
    return ModuleListResponse(modules=modules)

@router.get("/modules/{module_id}", response_model=ModuleResponse, status_code=status.HTTP_200_OK)
async def get_module_detail(module_id: str, current_user=Depends(get_current_user)):
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found."
        )
    
    # Check if user has access to the course containing this module
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": module["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    return ModuleResponse(
        moduleId=str(module["_id"]),
        courseId=str(module["course_id"]),
        name=module["name"],
        description=module["description"],
        createdAt=module["created_at"],
        status=module["status"]
    )