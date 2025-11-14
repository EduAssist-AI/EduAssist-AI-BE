"""
Summary Generation Utility Module
Handles generation of summaries from video transcripts using LLM
"""
import logging
from typing import List, Literal
from pydantic import BaseModel
from app.utils.llm_generator import LLMGenerator
from bson import ObjectId

logger = logging.getLogger(__name__)

# Define TranscriptSegment model since video_processor doesn't exist
class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str

class SummaryRequest(BaseModel):
    length_type: Literal["BRIEF", "DETAILED", "COMPREHENSIVE"]
    focus_areas: List[str] = []

class SummaryResponse(BaseModel):
    summaryId: str
    videoId: str  # Using videoId field name for compatibility, but can represent document ID too
    lengthType: str
    content: str
    wordCount: int
    version: int
    isPublished: bool

class SummaryGenerator:
    def __init__(self):
        self.llm_generator = LLMGenerator()

    def generate_summary_from_transcript(
        self,
        video_id: str,
        transcript_segments: List[TranscriptSegment],
        length_type: str = "BRIEF",
        focus_areas: List[str] = None
    ) -> str:
        """
        Generate a summary from video transcript using LLM
        """
        if not transcript_segments:
            return "No content available to summarize."

        # Combine transcript segments into a single text
        full_transcript = " ".join([segment.text.strip() for segment in transcript_segments if segment.text.strip()])

        # Create a prompt based on the requested summary type
        if length_type == "BRIEF":
            max_words = 100
            style = "concise and focused"
        elif length_type == "DETAILED":
            max_words = 300
            style = "comprehensive yet focused"
        else:  # COMPREHENSIVE
            max_words = 500
            style = "comprehensive and detailed"

        focus_instruction = ""
        if focus_areas:
            focus_instruction = f"Focus particularly on these areas: {', '.join(focus_areas)}. "

        prompt = f"""
        Please create a {style} summary of the following educational video transcript.
        {focus_instruction}
        The summary should highlight key concepts, main points, and important takeaways.
        Target length: approximately {max_words} words.

        Transcript:
        {full_transcript}

        Summary:
        """

        try:
            # Generate the summary using the LLM
            summary = self.llm_generator.generate_response(prompt)

            # Ensure the summary is within word limits if needed
            if length_type == "BRIEF" and len(summary.split()) > max_words * 1.2:
                # If it's too long, generate again with a more restrictive prompt
                prompt = f"""
                Please create a very concise summary (under {max_words} words) of the following educational video transcript.
                Focus only on the absolute most important key points.
                Transcript:
                {full_transcript}

                Summary (under {max_words} words):
                """
                summary = self.llm_generator.generate_response(prompt)

            return summary.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Return a basic summary if LLM fails
            return f"Summary generation failed. Transcript contains {len(full_transcript)} characters and {len(full_transcript.split())} words."

    async def store_summary_in_db(
        self,
        video_id: str,
        summary_content: str,
        length_type: str,
        resource_id: str = None  # Add optional resource_id parameter for documents
    ) -> str:
        """
        Store the generated summary in the database
        """
        from app.db.mongo import db
        import datetime

        # Create summary document - support both video_id and resource_id
        summary_doc = {
            "length_type": length_type,
            "content": summary_content,
            "word_count": len(summary_content.split()),
            "version": 1,  # Start with version 1
            "is_published": False,  # Default to unpublished
            "created_at": datetime.datetime.utcnow()
        }

        # Add video_id if provided (for videos), otherwise resource_id (for documents)
        if video_id:
            summary_doc["video_id"] = ObjectId(video_id)
        elif resource_id:
            summary_doc["resource_id"] = ObjectId(resource_id)

        result = await db["summaries"].insert_one(summary_doc)
        return str(result.inserted_id)

    async def generate_and_store_summary(
        self,
        video_id: str,
        transcript_segments: List[TranscriptSegment],
        length_type: str = "BRIEF",
        focus_areas: List[str] = None
    ) -> SummaryResponse:
        """
        Main method to generate and store a summary (for videos)
        """
        logger.info(f"Generating {length_type} summary for video {video_id}")

        # Generate the summary
        summary_content = self.generate_summary_from_transcript(
            video_id,
            transcript_segments,
            length_type,
            focus_areas or []
        )

        # Store the summary in database
        summary_id = await self.store_summary_in_db(video_id, summary_content, length_type)

        logger.info(f"Summary {summary_id} generated and stored for video {video_id}")

        return SummaryResponse(
            summaryId=summary_id,
            videoId=video_id,
            lengthType=length_type,
            content=summary_content,
            wordCount=len(summary_content.split()),
            version=1,
            isPublished=False
        )

    async def generate_and_store_document_summary(
        self,
        document_id: str,
        transcript_segments: List[TranscriptSegment],
        length_type: str = "BRIEF",
        focus_areas: List[str] = None
    ) -> SummaryResponse:
        """
        Main method to generate and store a summary for documents
        """
        logger.info(f"Generating {length_type} summary for document {document_id}")

        # Generate the summary
        # Create a more appropriate prompt for documents
        full_transcript = " ".join([segment.text.strip() for segment in transcript_segments if segment.text.strip()])

        # Create a prompt based on the requested summary type
        if length_type == "BRIEF":
            max_words = 100
            style = "concise and focused"
        elif length_type == "DETAILED":
            max_words = 300
            style = "comprehensive yet focused"
        else:  # COMPREHENSIVE
            max_words = 500
            style = "comprehensive and detailed"

        focus_instruction = ""
        if focus_areas:
            focus_instruction = f"Focus particularly on these areas: {', '.join(focus_areas)}. "

        prompt = f"""
        Please create a {style} summary of the following educational document content.
        {focus_instruction}
        The summary should highlight key concepts, main points, and important takeaways.
        Target length: approximately {max_words} words.

        Document Content:
        {full_transcript}

        Summary:
        """

        try:
            # Generate the summary using the LLM
            summary = self.llm_generator.generate_response(prompt)

            # Ensure the summary is within word limits if needed
            if length_type == "BRIEF" and len(summary.split()) > max_words * 1.2:
                # If it's too long, generate again with a more restrictive prompt
                prompt = f"""
                Please create a very concise summary (under {max_words} words) of the following educational document content.
                Focus only on the absolute most important key points.
                Document Content:
                {full_transcript}

                Summary (under {max_words} words):
                """
                summary = self.llm_generator.generate_response(prompt)
        except Exception as e:
            logger.error(f"Error generating document summary: {e}")
            # Return a basic summary if LLM fails
            summary = f"Summary generation failed. Document contains {len(full_transcript)} characters and {len(full_transcript.split())} words."

        # Store the summary in database with the document's resource_id
        summary_id = await self.store_summary_in_db(video_id=None, summary_content=summary, length_type=length_type, resource_id=document_id)

        logger.info(f"Summary {summary_id} generated and stored for document {document_id}")

        return SummaryResponse(
            summaryId=summary_id,
            videoId=document_id,  # Using videoId field as document_id to maintain compatibility
            lengthType=length_type,
            content=summary,
            wordCount=len(summary.split()),
            version=1,
            isPublished=False
        )