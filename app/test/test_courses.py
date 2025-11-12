import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.course import CourseCreate, CourseCreateResponse
from app.schemas.user import UserOut
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime
from typing import Dict, Any

# Suppress deprecation and other warnings for this test file
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")

# Test constants
test_email = "prit@gmail.com"
test_password = "12345"
test_username = "prit"
test_role = "FACULTY"
test_user_id = str(ObjectId())
test_course_id = str(ObjectId())
test_enrollment_id = str(ObjectId())

@pytest.fixture(scope="module")
def client():
    # Mock the authentication to return a faculty user using consistent credentials
    app.dependency_overrides[get_current_user] = lambda: {
        "id": test_user_id, 
        "username": test_username, 
        "email": test_email,
        "role": test_role
    }
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()

@pytest.fixture
def mock_db():
    with patch('app.routes.courses.db') as mock_db_instance:
        # Mock for bracket notation access (db["course_rooms"]...)
        mock_course_collection = AsyncMock()
        mock_enrollment_collection = AsyncMock()
        mock_module_collection = AsyncMock()
        
        # Create mock cursor objects for find operations
        mock_enrollment_cursor = AsyncMock()
        mock_course_cursor = AsyncMock()
        
        # Make find be a coroutine that returns the cursor (as it would be in motor)
        async def mock_find_enrollments(*args, **kwargs):
            return mock_enrollment_cursor
            
        async def mock_find_courses(*args, **kwargs):
            return mock_course_cursor
        
        mock_course_collection.find = mock_find_courses
        mock_enrollment_collection.find = mock_find_enrollments
        
        # Setup return values for course operations
        mock_course_collection.insert_one.return_value = type('obj', (object,), {'inserted_id': ObjectId(test_course_id)})()
        mock_course_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),
            "created_at": datetime.utcnow(),
            "status": "ACTIVE",
            "invitation_code": "TEST1234",
            "invitation_link": "/join/TEST1234"
        }
        
        # Mock the to_list method to be async (this is what the original code expects)
        mock_course_cursor.to_list = AsyncMock(return_value=[])
        mock_enrollment_cursor.to_list = AsyncMock(return_value=[])
        
        # Setup return values for enrollment operations
        mock_enrollment_collection.insert_one.return_value = type('obj', (object,), {'inserted_id': ObjectId(test_enrollment_id)})()
        mock_enrollment_collection.find_one.return_value = {
            "user_id": ObjectId(test_user_id), 
            "course_id": ObjectId(test_course_id),
            "role": test_role,
            "status": "ACTIVE"
        }  # Enrollment for the test user
        
        # Setup return values for module operations
        mock_module_collection.insert_one.return_value = type('obj', (object,), {'inserted_id': ObjectId()})()
        
        # Mock the collections
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "course_rooms": mock_course_collection,
            "enrollments": mock_enrollment_collection,
            "modules": mock_module_collection
        }[x]
        
        yield mock_db_instance

@pytest.mark.asyncio
async def test_create_course_success(client, mock_db):
    """Test successful course creation by a faculty user"""
    course_data = {
        "name": "New Test Course",
        "description": "This is a test course for testing purposes."
    }
    
    response = client.post("/api/v1/courses/", json=course_data)
    
    assert response.status_code == 201
    assert "courseId" in response.json()
    assert response.json()["name"] == course_data["name"]
    assert response.json()["description"] == course_data["description"]
    assert "invitationCode" in response.json()
    assert "invitationLink" in response.json()

@pytest.mark.asyncio
async def test_create_course_missing_fields(client, mock_db):
    """Test course creation with missing required fields"""
    course_data = {
        "description": "This is a test course without a name."
        # Missing required "name" field
    }
    
    response = client.post("/api/v1/courses/", json=course_data)
    
    assert response.status_code == 422  # Unprocessable Entity due to validation error

@pytest.mark.asyncio
async def test_create_course_short_name(client, mock_db):
    """Test course creation with a name that's too short"""
    course_data = {
        "name": "CS",  # Less than min length of 3
        "description": "This is a test course with a short name."
    }
    
    response = client.post("/api/v1/courses/", json=course_data)
    
    assert response.status_code == 422  # Validation error

@pytest.mark.asyncio
async def test_get_course_success(client, mock_db):
    """Test successful retrieval of a specific course"""
    # Setup enrollment for the user in this course
    mock_enrollment_collection = mock_db.__getitem__("enrollments")
    mock_enrollment_collection.find_one.return_value = {
        "user_id": ObjectId(test_user_id),
        "course_id": ObjectId(test_course_id),
        "role": test_role
    }
    
    response = client.get(f"/api/v1/courses/{test_course_id}")
    
    assert response.status_code == 200
    assert response.json()["courseId"] == test_course_id
    assert response.json()["name"] == "Test Course"

@pytest.mark.asyncio
async def test_get_course_not_enrolled(client, mock_db):
    """Test retrieving a course when not enrolled and not the creator"""
    # Mock that user is neither enrolled nor the creator
    mock_enrollment_collection = mock_db.__getitem__("enrollments")
    mock_course_collection = mock_db.__getitem__("course_rooms")
    
    # Temporarily override find_one to return None (not enrolled)
    async def temp_find_one_enrollment(*args, **kwargs):
        return None  # Not enrolled
    
    # Temporarily set this for the test
    original_find_one = mock_enrollment_collection.find_one
    mock_enrollment_collection.find_one = temp_find_one_enrollment
    
    # Make course creator a different user
    original_course_find_one = mock_course_collection.find_one
    mock_course_collection.find_one.return_value = {
        "_id": ObjectId(test_course_id),
        "name": "Test Course",
        "description": "Test Description",
        "created_by": ObjectId("507f1f77bcf86cd799439011"),  # Different creator
        "created_at": datetime.utcnow(),
        "status": "ACTIVE",
        "invitation_code": "TEST1234",
        "invitation_link": "/join/TEST1234"
    }
    
    response = client.get(f"/api/v1/courses/{test_course_id}")
    
    # Restore original mocks
    mock_enrollment_collection.find_one = original_find_one
    mock_course_collection.find_one = original_course_find_one
    
    assert response.status_code == 403  # Forbidden

@pytest.mark.asyncio
async def test_update_course_success(client, mock_db):
    """Test successful course update by the course creator"""
    course_data = {
        "name": "Updated Test Course",
        "description": "Updated description for the test course."
    }
    
    # Mock that the current user is the course creator
    mock_course_collection = mock_db.__getitem__("course_rooms")
    mock_course_collection.find_one.return_value = {
        "_id": ObjectId(test_course_id),
        "name": "Original Test Course",
        "description": "Original description",
        "created_by": ObjectId(test_user_id),  # Current user is creator
        "created_at": datetime.utcnow(),
        "status": "ACTIVE"
    }
    
    # Mock the update result to show one document was modified
    update_result_mock = AsyncMock()
    update_result_mock.modified_count = 1
    mock_course_collection.update_one.return_value = update_result_mock
    
    response = client.put(f"/api/v1/courses/{test_course_id}", json=course_data)
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert response.json()["course_id"] == test_course_id

@pytest.mark.asyncio
async def test_update_course_not_creator(client, mock_db):
    """Test updating a course when not the creator"""
    course_data = {
        "name": "Unauthorized Update",
        "description": "Should not be allowed."
    }
    
    # Mock that the current user is NOT the course creator
    mock_course_collection = mock_db.__getitem__("course_rooms")
    mock_course_collection.find_one.return_value = {
        "_id": ObjectId(test_course_id),
        "name": "Original Test Course",
        "description": "Original description",
        "created_by": ObjectId(),  # Different creator
        "created_at": datetime.utcnow(),
        "status": "ACTIVE"
    }
    
    response = client.put(f"/api/v1/courses/{test_course_id}", json=course_data)
    
    assert response.status_code == 403  # Forbidden