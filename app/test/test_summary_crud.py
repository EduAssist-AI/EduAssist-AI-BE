import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime
from app.schemas.summary import SummaryCreate

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

        # Create mock query result with skip/limit support
        mock_query_result = AsyncMock()

        async def mock_iterator():
            class AsyncIterator:
                def __init__(self, items):
                    self.items = items
                    self.index = 0

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self.index >= len(self.items):
                        raise StopAsyncIteration
                    item = self.items[self.index]
                    self.index += 1
                    return item

            return AsyncIterator([mock_summary_doc])

        mock_query_result.__aiter__.return_value = mock_iterator()
        mock_summaries_collection.find.return_value = mock_query_result
        mock_summaries_collection.find.return_value.skip.return_value = mock_query_result
        mock_summaries_collection.find.return_value.limit.return_value = mock_query_result
        mock_summaries_collection.find.return_value.skip.return_value.limit.return_value = mock_query_result

        # Mock count_documents for pagination
        mock_summaries_collection.count_documents.return_value = 1

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
async def test_create_summary_invalid_video_id(client, mock_db):
    """Test summary creation with invalid video ID"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup videos collection to return None (video not found)
        mock_videos_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_summaries_collection = AsyncMock()

        mock_videos_collection.find_one.return_value = None

        # Setup courses collection
        mock_courses_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),
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

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_videos_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "summaries": mock_summaries_collection
        }[x]

        summary_request = {
            "content": "Test summary content",
            "length_type": "BRIEF",
            "is_published": False,
            "video_id": str(ObjectId())
        }

        response = client.post("/api/v1/summaries", json=summary_request)

        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]


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
async def test_get_summary_not_found(client, mock_db):
    """Test retrieval of non-existent summary"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup summaries collection to return None (summary not found)
        mock_summaries_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()

        mock_summaries_collection.find_one.return_value = None

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "summaries": mock_summaries_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection
        }[x]

        response = client.get(f"/api/v1/summaries/{str(ObjectId())}")

        assert response.status_code == 404
        assert "Summary not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_summary_success(client, mock_db):
    """Test successful summary update"""
    # Update the mock to return updated summary data
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup same collections as in fixture
        mock_videos_collection = AsyncMock()
        mock_resources_collection = AsyncMock()
        mock_modules_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_summaries_collection = AsyncMock()

        # Setup courses collection (for access check)
        mock_courses_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }

        # Setup original summary
        original_summary = {
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

        # Setup updated summary
        updated_summary = {
            "_id": ObjectId(test_summary_id),
            "video_id": ObjectId(test_video_id),
            "module_id": ObjectId(test_module_id),
            "course_id": ObjectId(test_course_id),
            "length_type": "DETAILED",  # Updated value
            "content": "Updated summary content",  # Updated value
            "word_count": len("Updated summary content".split()),  # Updated word count
            "version": 1,
            "is_published": True,  # Updated value
            "focus_areas": ["main concepts"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        # Mock find_one to return original summary first, then updated summary
        async def side_effect_find_one(*args, **kwargs):
            # This will be called twice: once to get the original, once to return updated
            if str(args[0]) == {"_id": ObjectId(test_summary_id)}:
                return updated_summary  # Return the updated summary after update
            return original_summary

        mock_summaries_collection.find_one.side_effect = side_effect_find_one

        # Mock update result
        update_result = AsyncMock()
        update_result.modified_count = 1
        mock_summaries_collection.update_one.return_value = update_result

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "summaries": mock_summaries_collection
        }[x]

        update_request = {
            "content": "Updated summary content",
            "length_type": "DETAILED",
            "is_published": True
        }

        response = client.put(f"/api/v1/summaries/{test_summary_id}", json=update_request)

        assert response.status_code == 200
        assert "summaryId" in response.json()
        assert response.json()["summaryId"] == test_summary_id
        assert response.json()["lengthType"] == "DETAILED"  # This should now match
        assert response.json()["isPublished"] is True
        assert "Updated summary content" in response.json()["content"]


@pytest.mark.asyncio
async def test_update_summary_not_found(client, mock_db):
    """Test updating non-existent summary"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup summaries collection to return None (summary not found)
        mock_summaries_collection = AsyncMock()
        mock_courses_collection = AsyncMock()

        mock_summaries_collection.find_one.return_value = None

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "summaries": mock_summaries_collection,
            "course_rooms": mock_courses_collection
        }[x]

        update_request = {
            "content": "Updated content"
        }

        response = client.put(f"/api/v1/summaries/{str(ObjectId())}", json=update_request)

        assert response.status_code == 404
        assert "Summary not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_summary_success(client, mock_db):
    """Test successful summary deletion"""
    response = client.delete(f"/api/v1/summaries/{test_summary_id}")

    assert response.status_code == 200
    assert "Summary deleted successfully" in response.json()["message"]
    assert response.json()["summaryId"] == test_summary_id


@pytest.mark.asyncio
async def test_delete_summary_not_found(client, mock_db):
    """Test deleting non-existent summary"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup summaries collection to return None (summary not found)
        mock_summaries_collection = AsyncMock()

        mock_summaries_collection.find_one.return_value = None

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "summaries": mock_summaries_collection
        }[x]

        response = client.delete(f"/api/v1/summaries/{str(ObjectId())}")

        assert response.status_code == 404
        assert "Summary not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_module_summaries_success(client, mock_db):
    """Test successful retrieval of summaries for a specific module"""
    response = client.get(f"/api/v1/modules/{test_module_id}/summaries")

    assert response.status_code == 200
    assert "moduleId" in response.json()
    assert "summaries" in response.json()
    assert "pagination" in response.json()
    assert response.json()["moduleId"] == test_module_id
    assert isinstance(response.json()["summaries"], list)
    assert len(response.json()["summaries"]) > 0
    
    # Check that the first summary has the expected fields
    if response.json()["summaries"]:
        first_summary = response.json()["summaries"][0]
        assert "summaryId" in first_summary
        assert "content" in first_summary
        assert "lengthType" in first_summary


@pytest.mark.asyncio
async def test_get_module_summaries_not_found(client, mock_db):
    """Test retrieval of summaries when module doesn't exist"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup modules collection to return None (module not found)
        mock_modules_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()

        mock_modules_collection.find_one.return_value = None

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "modules": mock_modules_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection
        }[x]

        response = client.get(f"/api/v1/modules/{str(ObjectId())}/summaries")

        assert response.status_code == 404
        assert "Module not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_course_summaries_success(client, mock_db):
    """Test successful retrieval of summaries for a specific course"""
    response = client.get(f"/api/v1/courses/{test_course_id}/summaries")

    assert response.status_code == 200
    assert "summaries" in response.json()
    assert "pagination" in response.json()
    assert isinstance(response.json()["summaries"], list)
    assert len(response.json()["summaries"]) > 0
    
    # Check that the first summary has the expected fields
    if response.json()["summaries"]:
        first_summary = response.json()["summaries"][0]
        assert "summaryId" in first_summary
        assert "content" in first_summary
        assert "lengthType" in first_summary
        assert "courseId" in first_summary
        assert response.json()["summaries"][0]["courseId"] == test_course_id


@pytest.mark.asyncio
async def test_get_course_summaries_not_found(client, mock_db):
    """Test retrieval of summaries when course doesn't exist"""
    with patch('app.routes.summaries.db') as mock_db_instance:
        # Setup courses collection to return None (course not found)
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()

        mock_courses_collection.find_one.return_value = None

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection
        }[x]

        response = client.get(f"/api/v1/courses/{str(ObjectId())}/summaries")

        assert response.status_code == 404
        assert "Course not found" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__])