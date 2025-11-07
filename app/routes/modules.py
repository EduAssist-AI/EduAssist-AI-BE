from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.schemas.course import CourseCreate
from app.schemas.modules import ModuleCreate
from app.schemas.user import UserOut
from bson import ObjectId
from datetime import datetime
from typing import Dict, Any

router = APIRouter()

@router.post("/courses/{course_id}/modules")
async def create_module(course_id: str, module_data: ModuleCreate, current_user: UserOut = Depends(get_current_user)):
    # Verify course exists and user has permission
    course = await db["course_rooms"].find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    # Only course owner (faculty) can create modules
    if str(course["created_by"]) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only course owner can create modules")
    
    # Create module document
    module_doc = {
        "course_id": ObjectId(course_id),
        "name": module_data.name,
        "description": module_data.description,
        "created_at": datetime.utcnow(),
        "status": "ACTIVE",
        "created_by": ObjectId(current_user["id"])
    }
    
    result = await db["modules"].insert_one(module_doc)
    module_id = str(result.inserted_id)
    
    return {
        "moduleId": module_id,
        "courseId": course_id,
        "name": module_doc["name"],
        "description": module_doc["description"],
        "createdAt": module_doc["created_at"],
        "status": module_doc["status"]
    }

@router.get("/courses/{course_id}/modules")
async def list_modules(course_id: str, current_user: UserOut = Depends(get_current_user)):
    # Check if user is enrolled or is the course creator (faculty)
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")
    
    modules = await db["modules"].find({"course_id": ObjectId(course_id)}).to_list(length=100)
    
    # Format modules manually since ModuleOut doesn't exist
    module_list = []
    for module in modules:
        module_list.append({
            "moduleId": str(module["_id"]),
            "courseId": str(module["course_id"]),
            "name": module["name"],
            "description": module["description"],
            "createdAt": module["created_at"],
            "status": module["status"]
        })
    
    return {"modules": module_list}

@router.get("/modules/{module_id}")
async def get_module(module_id: str, current_user: UserOut = Depends(get_current_user)):
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    
    # Check if user is enrolled or is the course creator (faculty)
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    
    # Allow access if user is course creator (faculty) or enrolled student
    is_course_creator = str(course["created_by"]) == current_user["id"]
    is_enrolled = False
    
    if not is_course_creator:
        # Only check enrollment if user is not the course creator
        enrollment = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": module["course_id"]
        })
        is_enrolled = bool(enrollment)
    
    if not is_course_creator and not is_enrolled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")
    
    return {
        "moduleId": str(module["_id"]),
        "courseId": str(module["course_id"]),
        "name": module["name"],
        "description": module["description"],
        "createdAt": module["created_at"],
        "status": module["status"]
    }

@router.put("/modules/{module_id}")
async def update_module(module_id: str, module_data: ModuleCreate, current_user: UserOut = Depends(get_current_user)):
    # Get the module
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    
    # Verify user is course owner (faculty)
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only course owner can update module")
    
    # Update module
    update_data = {
        "$set": {
            "name": module_data.name,
            "description": module_data.description,
            "updated_at": datetime.utcnow()
        }
    }
    
    result = await db["modules"].update_one({"_id": ObjectId(module_id)}, update_data)
    
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes made to module")
    
    return {"message": "Module updated successfully", "module_id": module_id}

@router.delete("/modules/{module_id}")
async def delete_module(module_id: str, current_user: UserOut = Depends(get_current_user)):
    # Get the module
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    
    # Verify user is course owner (faculty)
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course or str(course["created_by"]) != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only course owner can delete module")
    
    # Check if there are any videos associated with this module
    video_count = await db["videos"].count_documents({"module_id": ObjectId(module_id)})
    if video_count > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                          detail="Cannot delete module with associated videos. Remove videos first.")
    
    # Delete module
    result = await db["modules"].delete_one({"_id": ObjectId(module_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module could not be deleted")
    
    return {"message": "Module deleted successfully", "module_id": module_id}