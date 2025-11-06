import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.modules import ModuleCreate
from app.schemas.user import UserOut
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime

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
test_module_id = str(ObjectId())

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
    with patch('app.routes.modules.db') as mock_db_instance:
        # Mock collections
        mock_course_collection = AsyncMock()
        mock_module_collection = AsyncMock()
        mock_enrollment_collection = AsyncMock()
        
        # Setup course collection
        mock_course_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }
        
        # Setup enrollment collection
        mock_enrollment_collection.find_one.return_value = {
            "user_id": ObjectId(test_user_id),
            "course_id": ObjectId(test_course_id),
            "role": test_role,
            "status": "ACTIVE"
        }
        
        # Setup module collection with insert_one
        mock_module_collection.insert_one.return_value = type('obj', (object,), {'inserted_id': ObjectId(test_module_id)})()
        
        # Mock other methods
        mock_module_collection.find_one.return_value = {
            "_id": ObjectId(test_module_id),
            "name": "Test Module",
            "description": "Test Description",
            "course_id": ObjectId(test_course_id),
            "created_at": datetime.utcnow(),
            "status": "ACTIVE",
            "created_by": ObjectId(test_user_id)
        }
        
        # Mock count_documents for delete check
        mock_module_collection.count_documents = AsyncMock(return_value=0)
        
        # Setup update and delete results
        update_result_mock = AsyncMock()
        update_result_mock.modified_count = 1
        mock_module_collection.update_one.return_value = update_result_mock
        
        delete_result_mock = AsyncMock()
        delete_result_mock.deleted_count = 1
        mock_module_collection.delete_one.return_value = delete_result_mock
        
        # Create a mock videos collection
        mock_videos_collection = AsyncMock()
        mock_videos_collection.count_documents = AsyncMock(return_value=0)
        
        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "course_rooms": mock_course_collection,
            "modules": mock_module_collection,
            "enrollments": mock_enrollment_collection,
            "videos": mock_videos_collection
        }[x]
        
        yield mock_db_instance

@pytest.mark.asyncio
async def test_create_module_success(client, mock_db):
    """Test successful module creation by a faculty user"""
    module_data = {
        "name": "New Test Module",
        "description": "This is a test module for testing purposes."
    }
    
    response = client.post(f"/api/v1/courses/{test_course_id}/modules", json=module_data)
    
    assert response.status_code == 200
    assert "moduleId" in response.json()
    assert response.json()["name"] == module_data["name"]
    assert response.json()["description"] == module_data["description"]
    assert response.json()["courseId"] == test_course_id

@pytest.mark.asyncio
async def test_create_module_missing_fields(client, mock_db):
    """Test module creation with missing required fields"""
    module_data = {
        "description": "This is a test module without a name."
        # Missing required "name" field
    }
    
    response = client.post(f"/api/v1/courses/{test_course_id}/modules", json=module_data)
    
    assert response.status_code == 422  # Unprocessable Entity due to validation error

@pytest.mark.asyncio
async def test_create_module_invalid_course(client, mock_db):
    """Test module creation for a non-existent course"""
    # Setup course to return None (not found)
    mock_course_collection = mock_db.__getitem__("course_rooms")
    mock_course_collection.find_one.return_value = None
    
    module_data = {
        "name": "Test Module for Invalid Course",
        "description": "This module should fail to create."
    }
    
    response = client.post(f"/api/v1/courses/{test_course_id}/modules", json=module_data)
    
    assert response.status_code == 404  # Course not found
    assert "detail" in response.json()

@pytest.mark.asyncio
async def test_get_module_success(client, mock_db):
    """Test successful retrieval of a specific module"""
    response = client.get(f"/api/v1/modules/{test_module_id}")
    
    assert response.status_code == 200
    assert response.json()["moduleId"] == test_module_id
    assert "name" in response.json()

@pytest.mark.asyncio
async def test_update_module_success(client, mock_db):
    """Test successful module update by the course owner"""
    module_data = {
        "name": "Updated Test Module",
        "description": "Updated description for the test module."
    }
    
    response = client.put(f"/api/v1/modules/{test_module_id}", json=module_data)
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert response.json()["module_id"] == test_module_id

@pytest.mark.asyncio
async def test_delete_module_success(client, mock_db):
    """Test successful module deletion by the course owner"""
    response = client.delete(f"/api/v1/modules/{test_module_id}")
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert response.json()["module_id"] == test_module_id