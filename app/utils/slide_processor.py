"""
Slide Parsing Utility Module
Handles parsing of presentation slides (PDF, PPTX) for educational content
Based on the implementation from slide_parsing_architecture.py
"""
import os
import tempfile
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.config import settings
import logging
import re

logger = logging.getLogger(__name__)


class SlideContent(BaseModel):
    slide_number: int
    text_content: str
    image_path: str
    features: List[str]
    bullets: List[str]


class SlideProcessor:
    def __init__(self):
        self.has_pymupdf = self._check_pymupdf_availability()
        self.has_python_pptx = self._check_pptx_availability()
        self.has_pytesseract = self._check_pytesseract_availability()
        self.has_clip = self._check_clip_availability()
        self.has_sentence_transformers = self._check_sentence_transformers_availability()
        self.has_faiss = self._check_faiss_availability()
    
    def _check_pymupdf_availability(self) -> bool:
        """Check if PyMuPDF (fitz) is available"""
        try:
            import fitz
            return True
        except ImportError:
            logger.warning("PyMuPDF is not installed. Install with: pip install PyMuPDF")
            return False
    
    def _check_pptx_availability(self) -> bool:
        """Check if python-pptx is available"""
        try:
            import pptx
            return True
        except ImportError:
            logger.warning("python-pptx is not installed. Install with: pip install python-pptx")
            return False

    def _check_pytesseract_availability(self) -> bool:
        """Check if Pytesseract is available"""
        try:
            import pytesseract
            return True
        except ImportError:
            logger.warning("Pytesseract is not installed. Install with: pip install pytesseract")
            return False

    def _check_clip_availability(self) -> bool:
        """Check if CLIP is available"""
        try:
            import clip
            return True
        except ImportError:
            logger.warning("CLIP is not installed. Install with: pip install clip")
            return False

    def _check_sentence_transformers_availability(self) -> bool:
        """Check if sentence-transformers is available"""
        try:
            import sentence_transformers
            return True
        except ImportError:
            logger.warning("sentence-transformers is not installed. Install with: pip install sentence-transformers")
            return False

    def _check_faiss_availability(self) -> bool:
        """Check if FAISS is available"""
        try:
            import faiss
            return True
        except ImportError:
            logger.warning("FAISS is not installed. Install with: pip install faiss-cpu")
            return False

    def convert_slides_to_images(self, file_path: str) -> List[str]:
        """
        Convert slides from PDF or PPTX to image format
        """
        if file_path.endswith('.pdf'):
            if not self.has_pymupdf:
                logger.error("PyMuPDF is required to process PDF files")
                return []
            return self._convert_pdf_to_images(file_path)
        elif file_path.endswith('.pptx'):
            if not self.has_python_pptx:
                logger.error("python-pptx is required to process PPTX files")
                return []
            return self._convert_pptx_to_images(file_path)
        else:
            logger.error("Unsupported file format. Only PDF and PPTX are supported.")
            return []

    def _convert_pdf_to_images(self, file_path: str, out_dir: Optional[str] = None) -> List[str]:
        """
        Convert PDF pages to images using PyMuPDF
        """
        import fitz
        
        if out_dir is None:
            out_dir = tempfile.mkdtemp()
        
        os.makedirs(out_dir, exist_ok=True)
        images = []
        
        doc = fitz.open(file_path)
        for i, page in enumerate(doc):
            pix = page.get_pixmap()
            img_path = os.path.join(out_dir, f"slide_{i}.png")
            pix.save(img_path)
            images.append(img_path)
        
        doc.close()
        return images

    def _convert_pptx_to_images(self, file_path: str, out_dir: Optional[str] = None) -> List[str]:
        """
        Convert PPTX slides to images
        Note: This is a simplified implementation.
        Full implementation would require rendering slides to images.
        """
        import pptx
        from PIL import Image, ImageDraw, ImageFont
        
        if out_dir is None:
            out_dir = tempfile.mkdtemp()
        
        os.makedirs(out_dir, exist_ok=True)
        images = []
        
        try:
            prs = pptx.Presentation(file_path)
            for i, slide in enumerate(prs.slides):
                img_path = os.path.join(out_dir, f"slide_{i}.png")
                
                # Create a placeholder image since full rendering requires additional dependencies
                # In a real implementation, you would render the actual slide content
                img = Image.new("RGB", (1280, 720), "white")
                d = ImageDraw.Draw(img)
                
                # Add slide number for identification
                d.text((10, 10), f"Slide {i}", fill=(0, 0, 0))
                
                img.save(img_path)
                images.append(img_path)
        except Exception as e:
            logger.error(f"Error converting PPTX to images: {e}")
            return []
        
        return images

    def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from image using OCR (Pytesseract)
        """
        if not self.has_pytesseract:
            logger.warning("Pytesseract not available, returning empty text")
            return ""
        
        try:
            from PIL import Image
            import pytesseract
            
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            
            # Clean the text
            text = self._clean_text(text)
            return text
        except Exception as e:
            logger.error(f"Error extracting text from image {image_path}: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by removing extra whitespace and formatting
        """
        text = text.replace('\n', ' ').replace('\f', '')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_bullets_from_text(self, text: str) -> List[str]:
        """
        Extract bullet points from text
        """
        # Split by common bullet characters and clean up
        bullets = [b.strip() for b in re.split(r'[\*•→\-\u2022]', text) if b.strip() and len(b.strip()) > 3]
        return bullets

    def chunk_text(self, text: str, max_words: int = 50) -> List[str]:
        """
        Split text into chunks of specified word count
        """
        words = text.split()
        return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]

    def process_slide_file(self, file_path: str) -> List[SlideContent]:
        """
        Main method to process a slide file (PDF/PPTX) and extract content
        """
        logger.info(f"Processing slide file: {file_path}")
        
        # Convert slides to images
        logger.info("Converting slides to images...")
        image_paths = self.convert_slides_to_images(file_path)
        
        if not image_paths:
            logger.error("No images were generated from the slide file")
            return []
        
        # Extract content from each image
        slide_contents = []
        for idx, img_path in enumerate(image_paths):
            # Extract text from image
            text_content = self.extract_text_from_image(img_path)
            
            # Extract bullet points
            bullets = self.extract_bullets_from_text(text_content)
            
            # Create slide content object
            slide_content = SlideContent(
                slide_number=idx,
                text_content=text_content,
                image_path=img_path,
                features=["text", "slide"],  # In a real implementation, you'd extract actual features
                bullets=bullets
            )
            
            slide_contents.append(slide_content)
        
        logger.info(f"Slide processing completed. Processed {len(slide_contents)} slides.")
        return slide_contents

    def search_content(self, query: str, slide_contents: List[SlideContent], k: int = 3) -> List[SlideContent]:
        """
        Search for content in slide contents (simplified implementation)
        In a real implementation, this would use embeddings and similarity search
        """
        # Simple keyword-based search as fallback
        results = []
        query_lower = query.lower()
        
        for slide in slide_contents:
            if query_lower in slide.text_content.lower():
                results.append(slide)
        
        # Return top k results
        return results[:k] if len(results) > k else results