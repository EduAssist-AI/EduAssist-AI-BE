import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime
from app.utils.summary_generator import SummaryRequest

# Suppress deprecation and other warnings for this test file
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")

# Test constants - using the same pattern as auth tests
test_email = "prit@gmail.com"
test_password = "12345"
test_username = "prit"
test_role = "FACULTY"
test_user_id = str(ObjectId())
test_video_id = str(ObjectId())
test_summary_id = str(ObjectId())

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
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_transcripts_collection = AsyncMock()
        mock_summaries_collection = AsyncMock()
        
        # Setup videos collection
        mock_videos_collection.find_one.return_value = {
            "_id": ObjectId(test_video_id),
            "title": "Test Video",
            "course_id": ObjectId(),
            "duration_seconds": 300,
            "status": "COMPLETE",
            "published": True,
            "published_at": datetime.utcnow(),
            "has_transcript": True,
            "has_summary": False,
            "has_quiz": True
        }
        
        # Setup courses collection
        mock_courses_collection.find_one.return_value = {
            "_id": ObjectId(),
            "name": "Test Course",
            "description": "Test Description",
            "created_by": ObjectId(test_user_id),  # Current user is the course creator
            "created_at": datetime.utcnow(),
            "status": "ACTIVE"
        }
        
        # Setup enrollments collection
        mock_enrollments_collection.find_one.return_value = {
            "user_id": ObjectId(test_user_id),
            "course_id": ObjectId(),  # Same course as video
            "role": test_role,
            "status": "ACTIVE"
        }
        
        # Setup transcripts collection (needed for summary generation)
        mock_transcripts_collection.find_one.return_value = {
            "_id": ObjectId(),
            "video_id": ObjectId(test_video_id),
            "segments": [
                {
                    "start": 0.0,
                    "end": 10.0,
                    "text": "This is the first segment of the video transcript."
                },
                {
                    "start": 10.0,
                    "end": 20.0,
                    "text": "This is the second segment of the video transcript."
                }
            ],
            "created_at": datetime.utcnow()
        }
        
        # Setup summaries collection for storing generated summaries
        insert_result = AsyncMock()
        insert_result.inserted_id = ObjectId(test_summary_id)
        mock_summaries_collection.insert_one.return_value = insert_result
        
        # Mock update for publish endpoint
        update_result = AsyncMock()
        update_result.modified_count = 1
        mock_summaries_collection.update_one.return_value = update_result
        
        # Mock summaries find_one for the publish endpoint
        mock_summaries_collection.find_one.return_value = {
            "_id": ObjectId(test_summary_id),
            "video_id": ObjectId(test_video_id),
            "content": "Test summary content",
            "length_type": "BRIEF",
            "word_count": 50,
            "version": 1,
            "is_published": False,
            "created_at": datetime.utcnow()
        }
        
        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_videos_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "transcripts": mock_transcripts_collection,
            "summaries": mock_summaries_collection
        }[x]
        
        yield mock_db_instance

@pytest.mark.asyncio
async def test_generate_summary_success(client, mock_db):
    """Test successful summary generation"""
    summary_request = {
        "length_type": "BRIEF",
        "focus_areas": ["main concepts", "key points"]
    }
    
    response = client.post(f"/api/v1/videos/{test_video_id}/summaries", json=summary_request)
    
    assert response.status_code == 201
    assert "summaryId" in response.json()
    assert "content" in response.json()
    assert "lengthType" in response.json()
    assert response.json()["lengthType"] == "BRIEF"

@pytest.mark.asyncio
async def test_generate_summary_detailed(client, mock_db):
    """Test detailed summary generation"""
    summary_request = {
        "length_type": "DETAILED",
        "focus_areas": []
    }
    
    response = client.post(f"/api/v1/videos/{test_video_id}/summaries", json=summary_request)
    
    assert response.status_code == 201
    assert "summaryId" in response.json()
    assert response.json()["lengthType"] == "DETAILED"

@pytest.mark.asyncio  
async def test_publish_summary_success(client, mock_db):
    """Test successful summary publishing"""
    request_data = {
        "isPublished": True
    }
    
    response = client.patch(f"/api/v1/summaries/{test_summary_id}/publish", json=request_data)
    
    assert response.status_code == 200
    assert "summaryId" in response.json()
    assert response.json()["summaryId"] == test_summary_id
    assert response.json()["isPublished"] is True