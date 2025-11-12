from typing import List, Optional
from pydantic import BaseModel, Field

class AddDocumentsRequest(BaseModel):
    documents: List[str] = Field(..., min_items=1)

class GenerateRagPromptRequest(BaseModel):
    query: str = Field(..., min_length=1)
    llm_prompt_template: str = Field(..., min_length=1)
    context_documents: Optional[List[str]] = Field(default_factory=list)  # Optional, if you want to add new documents on the fly

class GenerateRagPromptResponse(BaseModel):
    rag_prompt: str

class ExportEmbeddingsResponse(BaseModel):
    message: str
    file_path: str