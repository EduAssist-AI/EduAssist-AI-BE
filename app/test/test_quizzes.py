import pytest
import warnings
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
test_video_id = str(ObjectId())
test_quiz_id = str(ObjectId())
test_attempt_id = str(ObjectId())

@pytest.fixture(scope="module")
def client():
    # Mock the authentication to return a user using consistent credentials
    # NOTE: Quiz routes expect "_id" key, not "id"
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": test_user_id,
        "username": test_username,
        "email": test_email,
        "role": test_role
    }
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()

@pytest.fixture
def mock_db():
    with patch('app.routes.quizzes.db') as mock_db_instance:
        # Mock collections
        mock_videos_collection = AsyncMock()
        mock_courses_collection = AsyncMock()
        mock_enrollments_collection = AsyncMock()
        mock_quizzes_collection = AsyncMock()
        mock_quiz_attempts_collection = AsyncMock()

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
            "created_by": ObjectId(test_user_id),  # This should match the authenticated user ID
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

        # Setup quizzes collection
        mock_quizzes_collection.find_one.return_value = {
            "_id": ObjectId(test_quiz_id),
            "video_id": ObjectId(test_video_id),
            "title": "Test Quiz",
            "questions": [
                {
                    "question": "What is the capital of France?",
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "correctAnswer": "Paris",
                    "explanation": "Paris is the capital of France."
                }
            ],
            "is_published": True,
            "version": 1
        }

        # Mock find for quizzes (for get_quiz_list) - creating a proper async cursor mock
        class MockAsyncCursor:
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

        # Create quiz items
        quiz_items = [{
            "_id": ObjectId(test_quiz_id),
            "video_id": ObjectId(test_video_id),
            "title": "Test Quiz",
            "questions": [
                {
                    "question": "What is the capital of France?",
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "correctAnswer": "Paris",
                    "explanation": "Paris is the capital of France."
                }
            ],
            "is_published": True,
            "version": 1
        }]

        # Create a mock find method that returns an instance of MockAsyncCursor directly
        def mock_find_quizzes(*args, **kwargs):
            return MockAsyncCursor(quiz_items)

        mock_quizzes_collection.find = mock_find_quizzes

        # Setup quiz attempts collection
        insert_result = AsyncMock()
        insert_result.inserted_id = ObjectId(test_attempt_id)
        mock_quiz_attempts_collection.insert_one.return_value = insert_result

        # Mock the collections in the db object
        mock_db_instance.__getitem__.side_effect = lambda x: {
            "videos": mock_videos_collection,
            "course_rooms": mock_courses_collection,
            "enrollments": mock_enrollments_collection,
            "quizzes": mock_quizzes_collection,
            "quiz_attempts": mock_quiz_attempts_collection
        }[x]

        yield mock_db_instance

@pytest.mark.asyncio
async def test_get_quiz_list_success(client, mock_db):
    """Test successful retrieval of quiz list for a video"""
    response = client.get(f"/api/v1/videos/{test_video_id}/quizzes")

    assert response.status_code == 200
    assert "quizzes" in response.json()
    assert isinstance(response.json()["quizzes"], list)

@pytest.mark.asyncio
async def test_submit_quiz_attempt_success(client, mock_db):
    """Test successful quiz attempt submission"""
    quiz_answers = {
        "answers": [
            {
                "questionIndex": 0,
                "answer": "Paris"
            }
        ],
        "timeSpentSeconds": 120
    }

    response = client.post(f"/api/v1/quizzes/{test_quiz_id}/attempts", json=quiz_answers)

    assert response.status_code == 201
    assert "attemptId" in response.json()
    assert "score" in response.json()
    assert response.json()["score"] == 100  # Should be 100% since answer is correct
    assert response.json()["totalQuestions"] == 1
    assert response.json()["correctAnswers"] == 1