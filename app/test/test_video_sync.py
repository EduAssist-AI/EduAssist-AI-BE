import pytest
import warnings
import tempfile
import os
from fastapi.testclient import TestClient
from app.main import app
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
test_video_id = str(ObjectId())

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
    with patch('app.routes.videos.db') as mock_db_instance:
        # Mock collections
        mock_video_collection = AsyncMock()
        mock_course_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_transcript_collection = AsyncMock()
        
        # Setup course collection for permission checks
        mock_course_collection.find_one.return_value = {
            "_id": ObjectId(test_course_id),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),  # Current user is course creator
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }
        
        # Setup video collection
        mock_video_collection.insert_one.return_value = type('obj', (object,), {'inserted_id': ObjectId(test_video_id)})()
        
        # Setup transcript collection
        transcript_insert_result = AsyncMock()
        transcript_insert_result.inserted_id = ObjectId()
        mock_transcript_collection.insert_one.return_value = transcript_insert_result
        
        # Setup enrollment collection (for permission checks)
        mock_enrollments_collection.find_one.return_value = {
            "user_id": ObjectId(test_user_id),
            "course_id": ObjectId(test_course_id),
            "role": test_role,
            "status": "ACTIVE"
        }
        
        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_video_collection,
            "course_rooms": mock_course_collection,
            "enrollments": mock_enrollments_collection,
            "transcripts": mock_transcript_collection
        }[x]
        
        yield mock_db_instance

@pytest.mark.asyncio
async def test_upload_video_sync_success(client, mock_db):
    """Test successful synchronous video upload with upload_to_drive=False"""
    # Create a temporary file to simulate video upload
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        temp_video.write(b"fake video content")  # Write dummy content
        temp_video_path = temp_video.name

    try:
        with open(temp_video_path, "rb") as video_file:
            response = client.post(
                f"/api/v1/courses/{test_course_id}/videos-sync",
                data={"title": "Test Sync Video", "upload_to_drive": "false"},  # upload_to_drive=False
                files={"file": ("test_video.mp4", video_file, "video/mp4")}
            )
        
        assert response.status_code == 200
        assert "videoId" in response.json()
        assert response.json()["status"] == "COMPLETE"  # Should be complete since sync processing
        assert response.json()["title"] == "Test Sync Video"
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

@pytest.mark.asyncio
async def test_upload_video_sync_with_drive_true(client, mock_db):
    """Test synchronous video upload with upload_to_drive=True"""
    # Mock the Google Drive upload function
    with patch('app.routes.videos.upload_file_to_drive') as mock_upload_drive:
        mock_upload_drive.return_value = "fake_drive_file_id"
        
        # Create a temporary file to simulate video upload
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video content")  # Write dummy content
            temp_video_path = temp_video.name

        try:
            with open(temp_video_path, "rb") as video_file:
                response = client.post(
                    f"/api/v1/courses/{test_course_id}/videos-sync",
                    data={"title": "Test Drive Video", "upload_to_drive": "true"},  # upload_to_drive=True
                    files={"file": ("test_video.mp4", video_file, "video/mp4")}
                )
            
            assert response.status_code == 200
            assert "videoId" in response.json()
            assert response.json()["status"] == "COMPLETE"  # Should be complete since sync processing
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)

@pytest.mark.asyncio
async def test_upload_video_sync_invalid_course(client, mock_db):
    """Test synchronous video upload with non-existent course"""
    # Setup to return None (not found)
    mock_course_collection = mock_db.__getitem__("course_rooms")
    mock_course_collection.find_one.return_value = None
    
    # Create a temporary file to simulate video upload
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        temp_video.write(b"fake video content")  # Write dummy content
        temp_video_path = temp_video.name

    try:
        with open(temp_video_path, "rb") as video_file:
            response = client.post(
                f"/api/v1/courses/{test_course_id}/videos-sync",
                data={"title": "Test Video", "upload_to_drive": "false"},
                files={"file": ("test_video.mp4", video_file, "video/mp4")}
            )
        
        assert response.status_code == 404
        assert "detail" in response.json()
        assert "Course not found" in response.json()["detail"]
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)