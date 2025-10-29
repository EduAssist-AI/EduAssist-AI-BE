from typing import List
from .embeddings import Embeddings
from .chunking import TextChunker
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import chromadb
import uuid
import json # Import json for exporting
import os # Import os for path handling
from pydantic import BaseModel
from bson import ObjectId
import asyncio

# Define TranscriptSegment model
class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str

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

    def add_video_transcript_to_rag(self, video_id: str, transcript_segments: List[TranscriptSegment]):
        """
        Add video transcript segments to the RAG collection for semantic search
        """
        for segment in transcript_segments:
            text = segment.text
            if text.strip():  # Only add non-empty segments
                # Break down large segments if needed
                chunks = self.chunker.chunk_text(text)
                
                for i, chunk in enumerate(chunks):
                    embedding = self.embeddings.get_embedding(chunk)
                    
                    # Create metadata with video and segment information
                    metadata = {
                        "source": "video_transcript",
                        "video_id": video_id,
                        "start_time": segment.start,
                        "end_time": segment.end,
                        "segment_index": i
                    }
                    
                    self.collection.add(
                        embeddings=[embedding],
                        documents=[chunk],
                        metadatas=[metadata],
                        ids=[str(uuid.uuid4())]
                    )

    def search_video_content(self, query: str, video_id: str = None, top_k: int = 5) -> List[dict]:
        """
        Search for content in video transcripts
        """
        query_embedding = self.embeddings.get_embedding(query)
        
        # Build where clause if video_id is specified
        where_clause = None
        if video_id:
            where_clause = {"video_id": video_id}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=['documents', 'metadatas']
        )
        
        # Format results
        formatted_results = []
        if results['documents'] and results['metadatas']:
            for doc, metadata in zip(results['documents'][0], results['metadatas'][0]):
                formatted_results.append({
                    "content": doc,
                    "metadata": metadata
                })
        
        return formatted_results

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

async def add_video_content_to_rag(video_id: str, transcript_id: str, transcript_segments: List[TranscriptSegment]):
    """
    Async function to add video content to RAG system
    """
    from app.rag.generator import load_rag_generator
    rag_gen = load_rag_generator()
    
    # Add transcript segments to RAG
    rag_gen.add_video_transcript_to_rag(video_id, transcript_segments)
    
    print(f"Added {len(transcript_segments)} segments from video {video_id} to RAG system")


def load_rag_generator() -> RAGGenerator:
    """
    Loads and returns an instance of RAGGenerator.
    """
    return RAGGenerator()