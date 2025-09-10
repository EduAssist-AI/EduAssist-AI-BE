from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List
from app.utils.auth import get_current_user
from app.schemas.rag import AddDocumentsRequest, GenerateRagPromptRequest, GenerateRagPromptResponse, ExportEmbeddingsResponse


router = APIRouter()

@router.post("/add-documents", response_model=dict)
async def add_documents_to_rag(
    request_body: AddDocumentsRequest,
    request: Request,
    current_user=Depends(get_current_user) # Assuming authentication is required
):
    """
    Adds a list of documents to the RAG knowledge base.
    """
    rag_generator = request.app.state.rag_generator
    rag_generator.add_documents(request_body.documents)
    return {"message": "Documents added successfully to RAG knowledge base."}

@router.post("/generate-prompt", response_model=GenerateRagPromptResponse)
async def generate_rag_prompt_api(
    request_body: GenerateRagPromptRequest,
    request: Request,
    current_user=Depends(get_current_user) # Assuming authentication is required
):
    """
    Generates a RAG-augmented prompt based on a query and optional context documents.
    """
    rag_generator = request.app.state.rag_generator
    
    # If context_documents are provided in the request, add them to the RAG generator
    if request_body.context_documents:
        rag_generator.add_documents(request_body.context_documents)

    rag_prompt = rag_generator.generate_rag_prompt(
        query=request_body.query,
        documents=[], # Documents are already added or will be added via context_documents
        llm_prompt_template=request_body.llm_prompt_template
    )
    return GenerateRagPromptResponse(rag_prompt=rag_prompt)

@router.get("/export-embeddings", response_model=ExportEmbeddingsResponse)
async def export_rag_embeddings(
    request: Request,
    current_user=Depends(get_current_user) # Assuming authentication is required
):
    """
    Exports all embeddings and associated data from the ChromaDB collection.
    """
    rag_generator = request.app.state.rag_generator
    export_file_path = "TestPilotAI-BE/backend/exported_chroma_embeddings.json" # Define a specific path for export
    rag_generator.export_embeddings(file_path=export_file_path)
    return ExportEmbeddingsResponse(
        message="Embeddings exported successfully.",
        file_path=export_file_path
    )