from typing import List, Optional
from pydantic import BaseModel

class AddDocumentsRequest(BaseModel):
    documents: List[str]

class GenerateRagPromptRequest(BaseModel):
    query: str
    llm_prompt_template: str
    context_documents: Optional[List[str]] = None # Optional, if you want to add new documents on the fly

class GenerateRagPromptResponse(BaseModel):
    rag_prompt: str

class ExportEmbeddingsResponse(BaseModel):
    message: str
    file_path: str