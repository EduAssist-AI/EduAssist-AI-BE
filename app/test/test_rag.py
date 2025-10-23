import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.rag import AddDocumentsRequest, GenerateRagPromptRequest, GenerateRagPromptResponse, ExportEmbeddingsResponse
from app.utils.auth import get_current_user
from unittest.mock import AsyncMock, patch
from bson import ObjectId

# Suppress all warnings for this test file
warnings.filterwarnings("ignore")

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
def mock_rag_generator():
    with patch('app.rag.generator.load_rag_generator') as mock_load_rag_gen:
        mock_instance = AsyncMock()
        mock_instance.add_documents.return_value = None
        mock_instance.generate_rag_prompt.return_value = "Generated RAG prompt."
        mock_instance.export_embeddings.return_value = None
        mock_load_rag_gen.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_add_documents_to_rag(client: TestClient, mock_rag_generator):
    documents = ["doc1", "doc2"]
    request_body = AddDocumentsRequest(documents=documents)
    response = client.post("/rag/add-documents", json=request_body.model_dump())
    
    assert response.status_code == 200
    assert "message" in response.json()
    # Note: For real implementation, the app state rag_generator is used, not the mock object passed to test
    # So the mock object's calls won't be recorded in this specific integration test

@pytest.mark.asyncio
async def test_generate_rag_prompt_without_context(client: TestClient, mock_rag_generator):
    query = "What is the capital of France?"
    llm_prompt_template = "Question: {query}\nAnswer:"
    request_body = GenerateRagPromptRequest(query=query, llm_prompt_template=llm_prompt_template)
    response = client.post("/rag/generate-prompt", json=request_body.model_dump())
    
    assert response.status_code == 200
    assert "rag_prompt" in response.json()
    # The response should contain the query as part of the prompt since that's how the template works
    assert query in response.json()["rag_prompt"]

@pytest.mark.asyncio
async def test_generate_rag_prompt_with_context(client: TestClient, mock_rag_generator):
    query = "what is the year today?"
    context_documents = ["context1", "context2"]
    llm_prompt_template = "Context: {context}\nQuestion: {query}\nAnswer:"
    request_body = GenerateRagPromptRequest(query=query, context_documents=context_documents, llm_prompt_template=llm_prompt_template)
    response = client.post("/rag/generate-prompt", json=request_body.model_dump())
    
    assert response.status_code == 200
    assert "rag_prompt" in response.json()
    # The response should contain the query as part of the prompt since that's how the template works
    assert query in response.json()["rag_prompt"]
    # The template should be applied, creating a prompt with context and question sections
    assert "Question:" in response.json()["rag_prompt"] and "Answer:" in response.json()["rag_prompt"]

