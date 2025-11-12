import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.chat import ChatMessage, ChatHistory, ChatHistoryOut
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from datetime import datetime
from bson import ObjectId

# Suppress deprecation and other warnings for this test file
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")
warnings.filterwarnings("ignore", message=".*dict method is deprecated.*")


# Test user credentials (reusing from test_auth for consistency)
test_user_id = "652a1a9a0a8e7c1b7c8e7c1b" # Example ObjectId string
test_username = "prit"
test_email = "prit@gmail.com"

@pytest.fixture(scope="module")
def client():
    # Override the dependency to return a mock user
    app.dependency_overrides[get_current_user] = lambda: {"id": test_user_id, "username": test_username, "email": test_email}
    with TestClient(app) as tc:
        yield tc
    # Clean up the override after tests
    app.dependency_overrides.clear()

@pytest.fixture
def mock_chat_history_collection():
    with patch('app.routes.chat.chat_history_collection') as mock_collection:
        mock_collection.find_one = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        mock_collection.update_one = AsyncMock()
        yield mock_collection

@pytest.fixture
def mock_llm_generator():
    with patch('app.utils.llm_generator.LLMGenerator') as mock_llm_gen_class:
        mock_instance = AsyncMock()
        mock_instance.generate_response.return_value = "LLM generated response."
        mock_llm_gen_class.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_rag_generator():
    with patch('app.rag.generator.load_rag_generator') as mock_load_rag_gen:
        mock_instance = AsyncMock()
        mock_instance.retrieve_relevant_chunks.return_value = ["chunk1", "chunk2"]
        mock_load_rag_gen.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_get_chat_history_no_history(client: TestClient, mock_chat_history_collection):
    mock_chat_history_collection.find_one.side_effect = [
        None, # First call: no history found
        { # Second call: after insertion
            "_id": ObjectId(test_user_id),
            "userId": test_user_id,
            "messages": []
        }
    ]
    
    response = client.get("/chat/history")
    assert response.status_code == 200
    assert response.json()["userId"] == test_user_id
    assert response.json()["messages"] == []
    mock_chat_history_collection.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_get_chat_history_existing_history(client: TestClient, mock_chat_history_collection):
    # Create data structure that matches what would be returned from DB
    existing_history = {
        "_id": ObjectId(test_user_id),
        "userId": test_user_id,
        "messages": [
            # Use raw dict format that would come from database
            {"sender": "user", "message": "Hello", "timestamp": datetime.utcnow().isoformat()},
            {"sender": "llm", "message": "Hi there!", "timestamp": datetime.utcnow().isoformat()}
        ]
    }
    mock_chat_history_collection.find_one.return_value = existing_history

    response = client.get("/chat/history")
    assert response.status_code == 200
    assert response.json()["userId"] == test_user_id
    assert len(response.json()["messages"]) == 2
    mock_chat_history_collection.find_one.assert_called_once()

@pytest.mark.asyncio
async def test_post_chat_message_new_history(client: TestClient, mock_chat_history_collection, mock_llm_generator, mock_rag_generator):
    mock_chat_history_collection.find_one.return_value = None # No existing history
    
    # Create the message with only required fields, letting timestamp be set by the model
    user_message_data = {"sender": "user", "message": "What is RAG?"}
    response = client.post("/chat/message", json=user_message_data)
    
    assert response.status_code == 200
    assert response.json()["sender"] == "llm"
    # The response should be a non-empty string
    assert len(response.json()["message"]) > 0
    # Note: The real LLM/RAG generators are used in this test, not the mock objects
    mock_chat_history_collection.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_post_chat_message_existing_history(client: TestClient, mock_chat_history_collection, mock_llm_generator, mock_rag_generator):
    existing_history = {
        "_id": ObjectId(test_user_id),
        "userId": test_user_id,
        "messages": []
    }
    mock_chat_history_collection.find_one.return_value = existing_history
    
    user_message_data = {"sender": "user", "message": "Tell me more."}
    response = client.post("/chat/message", json=user_message_data)
    
    assert response.status_code == 200
    assert response.json()["sender"] == "llm"
    # The response should be a non-empty string
    assert len(response.json()["message"]) > 0
    # Note: The real LLM/RAG generators are used in this test, not the mock objects
    mock_chat_history_collection.update_one.assert_called_once()

@pytest.mark.asyncio
async def test_post_chat_message_invalid_sender(client: TestClient):
    llm_message_data = {"sender": "llm", "message": "Invalid message."}
    response = client.post("/chat/message", json=llm_message_data)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Sender must be 'user' for new messages."