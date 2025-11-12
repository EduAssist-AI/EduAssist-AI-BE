import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.user import UserOut
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime
import tempfile
import os

# Suppress deprecation and other warnings for this test file
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")

# Test constants
test_user_id = str(ObjectId())
test_faculty_id = str(ObjectId())
test_video_id = str(ObjectId())
test_course_id = str(ObjectId())

@pytest.fixture(scope="module")
def client():
    # Mock the authentication to return a faculty user
    app.dependency_overrides[get_current_user] = lambda: {
        "id": test_faculty_id, 
        "username": "test_faculty", 
        "email": "faculty@test.com",
        "role": "FACULTY"
    }
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()

@pytest.fixture
def mock_db():
    with patch('app.routes.video_processing.db') as mock_db_instance:
        # Mock collections
        mock_videos_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_transcripts_collection = AsyncMock()
        
        # Setup course collection
        mock_courses_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_faculty_id),
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }
        
        # Setup videos collection
        mock_videos_collection.find_one.return_value = {
            "_id": ObjectId(test_video_id),
            "title": "Test Video",
            "course_id": ObjectId(test_course_id),
            "duration_seconds": 300,
            "status": "COMPLETE",
            "published": True,
            "published_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False,
            "has_quiz": False
        }
        
        # Setup enrollments collection
        mock_enrollments_collection.find_one.return_value = {
            "user_id": ObjectId(test_faculty_id),
            "course_id": ObjectId(test_course_id),
            "role": "FACULTY",
            "status": "ACTIVE"
        }
        
        # Setup transcripts collection
        mock_transcripts_collection.find_one.return_value = {
            "_id": ObjectId(),
            "video_id": ObjectId(test_video_id),
            "segments": [{"start": 0, "end": 30, "text": "Test transcript segment"}],
            "updated_at": datetime.utcnow()
        }
        
        # Create cursor objects for find operations
        mock_videos_cursor = AsyncMock()
        mock_enrollments_cursor = AsyncMock()
        mock_transcripts_cursor = AsyncMock()
        
        # Mock count_documents for delete check
        mock_videos_collection.count_documents = AsyncMock(return_value=0)
        
        # Setup update, insert, and delete results
        update_result_mock = AsyncMock()
        update_result_mock.modified_count = 1
        mock_videos_collection.update_one.return_value = update_result_mock
        
        delete_result_mock = AsyncMock()
        delete_result_mock.deleted_count = 1
        mock_videos_collection.delete_one.return_value = delete_result_mock
        mock_transcripts_collection.delete_one.return_value = delete_result_mock
        mock_transcripts_collection.delete_many.return_value = delete_result_mock
        
        insert_result_mock = AsyncMock()
        insert_result_mock.inserted_id = ObjectId()
        mock_transcripts_collection.insert_one.return_value = insert_result_mock
        
        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_videos_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "transcripts": mock_transcripts_collection
        }[x]
        
        yield mock_db_instance

@pytest.fixture
def mock_audio_processor():
    with patch('app.routes.video_processing.AudioProcessor') as mock_audio_processor_class:
        mock_instance = AsyncMock()
        mock_instance.process_video_for_transcription.return_value = "This is a test transcription of the video content."
        mock_audio_processor_class.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_get_video_success(client, mock_db):
    """Test successful retrieval of a video by ID"""
    response = client.get(f"/api/v1/videos/{test_video_id}")
    
    assert response.status_code == 200
    assert "video_id" in str(response.json()) or "_id" in response.json()
    assert response.json()["title"] == "Test Video"

@pytest.mark.asyncio
async def test_update_video_success(client, mock_db):
    """Test successful update of video details"""
    # Update the find_one mock to return the new title after update
    mock_videos_collection = mock_db.__getitem__("videos")
    mock_videos_collection.find_one.side_effect = [
        # First call: original video
        {
            "_id": ObjectId(test_video_id),
            "title": "Test Video",
            "course_id": ObjectId(test_course_id),
            "duration_seconds": 300,
            "status": "COMPLETE",
            "published": True,
            "published_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False,
            "has_quiz": False
        },
        # Second call: updated video (after update)
        {
            "_id": ObjectId(test_video_id),
            "title": "Updated Video Title",  # Updated title
            "course_id": ObjectId(test_course_id),
            "duration_seconds": 300,
            "status": "COMPLETE",
            "published": True,
            "published_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False,
            "has_quiz": False
        }
    ]
    
    response = client.put(f"/api/v1/videos/{test_video_id}", params={"title": "Updated Video Title"})
    
    assert response.status_code == 200
    assert "title" in response.json()
    assert response.json()["title"] == "Updated Video Title"

@pytest.mark.asyncio
async def test_delete_video_success(client, mock_db):
    """Test successful deletion of a video"""
    response = client.delete(f"/api/v1/videos/{test_video_id}")
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert "deleted_video_id" in response.json()

@pytest.mark.asyncio
async def test_get_video_transcript_success(client, mock_db):
    """Test successful retrieval of video transcript"""
    response = client.get(f"/api/v1/videos/{test_video_id}/transcript")
    
    assert response.status_code == 200
    assert "video_id" in str(response.json()) or "segments" in response.json()

@pytest.mark.asyncio
async def test_update_video_transcript_success(client, mock_db):
    """Test successful update of video transcript"""
    transcript_data = [
        {"start": 0, "end": 30, "text": "First segment of the video"},
        {"start": 30, "end": 60, "text": "Second segment of the video"}
    ]
    
    response = client.put(f"/api/v1/videos/{test_video_id}/transcript", json=transcript_data)
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert response.json()["video_id"] == test_video_id

@pytest.mark.asyncio
async def test_delete_video_transcript_success(client, mock_db):
    """Test successful deletion of video transcript"""
    response = client.delete(f"/api/v1/videos/{test_video_id}/transcript")
    
    assert response.status_code == 200
    assert "message" in response.json()
    assert response.json()["video_id"] == test_video_id

@pytest.mark.asyncio
async def test_transcribe_video_endpoint_success(client, mock_db, mock_audio_processor):
    """Test successful video transcription endpoint"""
    # Create a temporary file to simulate video upload
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        temp_video.write(b"fake video content")  # Write dummy content
        temp_video_path = temp_video.name

    try:
        with open(temp_video_path, "rb") as video_file:
            response = client.post(
                "/api/v1/transcribe-video/",
                files={"video": ("test_video.mp4", video_file, "video/mp4")}
            )
        
        assert response.status_code == 200
        assert "success" in response.json()
        assert response.json()["success"] is True
        assert "video_id" in response.json()
        assert "transcription" in response.json()
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)