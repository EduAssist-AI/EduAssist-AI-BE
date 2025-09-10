from typing import List
from .embeddings import Embeddings
from .chunking import TextChunker
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import chromadb
import uuid
import json # Import json for exporting
import os # Import os for path handling

class RAGGenerator:
    def __init__(self, embedding_model_name="sentence-transformers/all-MiniLM-L6-v2", chunk_size=512, chunk_overlap=50, collection_name="rag_collection", persist_directory="./chroma_db"):
        self.embeddings = Embeddings(model_name=embedding_model_name)
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Initialize ChromaDB client with a persistent directory
        self.persist_directory = persist_directory
        self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(name=collection_name)

    def add_documents(self, documents: List[str]):
        for doc in documents:
            chunks = self.chunker.chunk_text(doc)
            for chunk in chunks:
                embedding = self.embeddings.get_embedding(chunk)
                self.collection.add(
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"source": "document"}], # You can add more meaningful metadata
                    ids=[str(uuid.uuid4())]
                )

    def retrieve_relevant_chunks(self, query: str, top_k: int = 3) -> List[str]:
        query_embedding = self.embeddings.get_embedding(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=['documents']
        )
        
        return results['documents'][0] if results['documents'] else []

    def generate_rag_prompt(self, query: str, documents: List[str], llm_prompt_template: str) -> str:
        self.add_documents(documents)
        relevant_chunks = self.retrieve_relevant_chunks(query)
        
        context = "\n".join(relevant_chunks)
        
        # Integrate context into the LLM prompt template
        rag_prompt = llm_prompt_template.format(context=context, query=query)
        return rag_prompt

    def export_embeddings(self, file_path: str = "chroma_embeddings_export.json"):
        """
        Exports all embeddings, documents, and metadatas from the ChromaDB collection to a JSON file.
        """
        all_data = self.collection.get(
            ids=None,
            where=None,
            limit=None,
            offset=None,
            include=['documents', 'embeddings', 'metadatas']
        )
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

        with open(file_path, "w") as f:
            json.dump(all_data, f, indent=4)
        print(f"Embeddings exported to {file_path}")

def load_rag_generator() -> RAGGenerator:
    """
    Loads and returns an instance of RAGGenerator.
    """
    return RAGGenerator()