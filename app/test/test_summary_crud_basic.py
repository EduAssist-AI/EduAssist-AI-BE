import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
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
test_video_id = str(ObjectId())
test_resource_id = str(ObjectId())
test_summary_id = str(ObjectId())
test_module_id = str(ObjectId())
test_course_id = str(ObjectId())

@pytest.fixture(scope="module")
def client():
    # Mock the authentication to return a user using consistent credentials
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
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Mock collections
        mock_videos_collection = AsyncMock()
        mock_resources_collection = AsyncMock()
        mock_modules_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_summaries_collection = AsyncMock()

        # Setup videos collection
        mock_videos_collection.find_one.return_value = {
            "_id": ObjectId(test_video_id),
            "title": "Test Video",
            "course_id": ObjectId(test_course_id),
            "module_id": ObjectId(test_module_id),
            "duration_seconds": 300,
            "status": "COMPLETE",
            "published": True,
            "published_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False,
            "has_quiz": True
        }

        # Setup resources collection
        mock_resources_collection.find_one.return_value = {
            "_id": ObjectId(test_resource_id),
            "title": "Test Resource",
            "course_id": ObjectId(test_course_id),
            "module_id": ObjectId(test_module_id),
            "type": "pdf",
            "status": "COMPLETE",
            "published": True,
            "uploaded_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False
        }

        # Setup modules collection
        mock_modules_collection.find_one.return_value = {
            "_id": ObjectId(test_module_id),
            "course_id": ObjectId(test_course_id),
            "name": "Test Module",
            "description": "Test Description",
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }

        # Setup courses collection
        mock_courses_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),  # Current user is the course creator
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }

        # Setup enrollments collection
        mock_enrollments_collection.find_one.return_value = {
            "user_id": ObjectId(test_user_id),
            "course_id": ObjectId(test_course_id),
            "role": test_role,
            "status": "ACTIVE"
        }

        # Setup summaries collection
        insert_result = AsyncMock()
        insert_result.inserted_id = ObjectId(test_summary_id)
        mock_summaries_collection.insert_one.return_value = insert_result

        # Mock find for retrieving summaries
        mock_summary_doc = {
            "_id": ObjectId(test_summary_id),
            "video_id": ObjectId(test_video_id),
            "module_id": ObjectId(test_module_id),
            "course_id": ObjectId(test_course_id),
            "length_type": "BRIEF",
            "content": "Test summary content",
            "word_count": 50,
            "version": 1,
            "is_published": False,
            "focus_areas": ["main concepts"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        mock_summaries_collection.find_one.return_value = mock_summary_doc
        
        # Mock update and delete operations
        update_result = AsyncMock()
        update_result.modified_count = 1
        mock_summaries_collection.update_one.return_value = update_result
        
        delete_result = AsyncMock()
        delete_result.deleted_count = 1
        mock_summaries_collection.delete_one.return_value = delete_result

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_videos_collection,
            "resources": mock_resources_collection,
            "modules": mock_modules_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "summaries": mock_summaries_collection
        }[x]

        yield mock_db_instance


@pytest.mark.asyncio
async def test_create_summary_success(client, mock_db):
    """Test successful summary creation with module association"""
    summary_request = {
        "content": "Test summary content for module",
        "length_type": "BRIEF",
        "focus_areas": ["main concepts", "key points"],
        "is_published": False,
        "video_id": test_video_id
    }

    response = client.post("/api/v1/summaries", json=summary_request)

    assert response.status_code == 201
    assert "summaryId" in response.json()
    assert "content" in response.json()
    assert "moduleId" in response.json()
    assert response.json()["lengthType"] == "BRIEF"
    assert response.json()["videoId"] == test_video_id


@pytest.mark.asyncio
async def test_create_summary_with_resource(client, mock_db):
    """Test successful summary creation with resource association"""
    summary_request = {
        "content": "Test summary from resource",
        "length_type": "DETAILED",
        "focus_areas": ["technical details"],
        "is_published": True,
        "resource_id": test_resource_id
    }

    response = client.post("/api/v1/summaries", json=summary_request)

    assert response.status_code == 201
    assert "summaryId" in response.json()
    assert "resourceId" in response.json()
    assert response.json()["lengthType"] == "DETAILED"
    assert response.json()["resourceId"] == test_resource_id
    assert response.json()["isPublished"] is True


@pytest.mark.asyncio
async def test_create_summary_missing_content(client, mock_db):
    """Test summary creation with missing content"""
    summary_request = {
        "length_type": "BRIEF",
        "focus_areas": ["main concepts"],
        "is_published": False,
        "video_id": test_video_id
    }

    response = client.post("/api/v1/summaries", json=summary_request)

    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_get_summary_success(client, mock_db):
    """Test successful retrieval of a summary"""
    response = client.get(f"/api/v1/summaries/{test_summary_id}")

    assert response.status_code == 200
    assert "summaryId" in response.json()
    assert response.json()["summaryId"] == test_summary_id
    assert "content" in response.json()
    assert "moduleId" in response.json()


@pytest.mark.asyncio
async def test_delete_summary_success(client, mock_db):
    """Test successful summary deletion"""
    response = client.delete(f"/api/v1/summaries/{test_summary_id}")

    assert response.status_code == 200
    assert "Summary deleted successfully" in response.json()["message"]
    assert response.json()["summaryId"] == test_summary_id


if __name__ == "__main__":
    pytest.main([__file__])