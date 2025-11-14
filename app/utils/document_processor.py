"""
Document processing utilities for EduAssist-AI application
Handles processing of PDF, DOCX, and TXT files
"""

import os
import logging
from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF for PDF processing (imported as fitz)
from docx import Document as DocxDocument  # python-docx for DOCX processing

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Handles document processing for PDF, DOCX, and TXT files"""

    def __init__(self):
        """Initialize the document processor"""
        # Create uploads/documents directory if it doesn't exist
        doc_dir = Path("uploads") / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)
        self.doc_dir = doc_dir

    def read_pdf(self, file_path: str) -> Optional[str]:
        """
        Extract text from PDF file

        Args:
            file_path: Path to the PDF file

        Returns:
            Extracted text content, or None if extraction failed
        """
        try:
            doc = fitz.open(file_path)
            text_content = ""

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Extract text with better formatting, including images if needed
                text = page.get_text("text")  # Use "text" option for better text extraction
                text_content += text + "\n"

            doc.close()
            return text_content.strip()
        except Exception as e:
            logger.error(f"Error reading PDF file {file_path}: {e}")
            # Try alternative method if the first one fails
            try:
                import pdfplumber
                text_content = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_content += text + "\n"
                return text_content.strip()
            except Exception as e2:
                logger.error(f"Error reading PDF file {file_path} with alternative method: {e2}")
                return None

    def read_docx(self, file_path: str) -> Optional[str]:
        """
        Extract text from DOCX file

        Args:
            file_path: Path to the DOCX file

        Returns:
            Extracted text content, or None if extraction failed
        """
        try:
            doc = DocxDocument(file_path)
            paragraphs = [paragraph.text for paragraph in doc.paragraphs]
            return "\n".join(paragraphs).strip()
        except Exception as e:
            logger.error(f"Error reading DOCX file {file_path}: {e}")
            return None

    def read_txt(self, file_path: str) -> Optional[str]:
        """
        Extract text from TXT file

        Args:
            file_path: Path to the TXT file

        Returns:
            Extracted text content, or None if extraction failed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Error reading TXT file {file_path}: {e}")
            return None

    def process_document(self, file_path: str, file_type: str) -> Optional[str]:
        """
        Process document based on its type

        Args:
            file_path: Path to the document file
            file_type: Type of document ('pdf', 'docx', 'txt')

        Returns:
            Extracted text content, or None if processing failed
        """
        logger.info(f"Processing {file_type.upper()} document: {file_path}")

        if file_type.lower() == 'pdf':
            return self.read_pdf(file_path)
        elif file_type.lower() == 'docx':
            return self.read_docx(file_path)
        elif file_type.lower() == 'txt':
            return self.read_txt(file_path)
        else:
            logger.error(f"Unsupported document type: {file_type}")
            return None

    async def save_document_content(self, content: str, resource_id: str) -> Optional[str]:
        """
        Save document content to database as transcript

        Args:
            content: Extracted text content
            resource_id: ID of the resource to store content for

        Returns:
            Status message or None if failed
        """
        try:
            from app.db.mongo import db
            from bson import ObjectId
            from datetime import datetime

            # Create transcript document for the processed content
            # For documents, we use start=0, end=0 since there's no temporal aspect
            transcript_doc = {
                "resource_id": ObjectId(resource_id),
                "segments": [
                    {
                        "start": 0.0,  # Start time is 0 for documents
                        "end": 0.0,    # End time is 0 for documents (no temporal aspect)
                        "text": content  # Store the full document content
                    }
                ],
                "word_count": len(content.split()) if content else 0,
                "language": "en",  # Default language, could be detected
                "confidence": 1.0,  # Full confidence since it's raw text
                "created_at": datetime.utcnow()
            }

            # Store in the transcripts collection (as requested)
            result = await db["transcripts"].insert_one(transcript_doc)
            transcript_id = str(result.inserted_id)

            logger.info(f"Document content saved as transcript {transcript_id} for resource {resource_id}")
            return f"Document content saved successfully as transcript {transcript_id}"
        except Exception as e:
            logger.error(f"Error saving document content as transcript for resource {resource_id}: {e}")
            return None