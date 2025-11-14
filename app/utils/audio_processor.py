"""
Audio processing utilities for EduAssist-AI application
Handles video to audio conversion and Whisper transcription
"""

import os
import logging
import uuid
import tempfile
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioProcessor:
    """Handles audio extraction and processing for video files"""
    
    def __init__(self):
        """Initialize the audio processor"""
        # Create uploads/audio directory if it doesn't exist
        audio_dir = Path("uploads") / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir = audio_dir
    
    def convert_video_to_audio(self, video_path: str) -> Optional[str]:
        """
        Convert video to audio using MoviePy and pydub for Whisper compatibility

        Args:
            video_path: Path to the input video file

        Returns:
            Path to the processed audio file, or None if conversion failed
        """
        try:
            # Import required libraries inside the function to avoid issues if not installed
            try:
                from moviepy.editor import VideoFileClip  # Updated import for newer versions
            except ImportError:
                from moviepy import VideoFileClip  # Fallback for older versions
            from pydub import AudioSegment
            import gc
            import time

            if not os.path.exists(video_path):
                logger.error(f"Video file does not exist: {video_path}")
                return None

            # Generate temporary file names
            temp_uuid = str(uuid.uuid4())
            temp_audio_path = str(self.audio_dir / f"temp_original_{temp_uuid}.wav")
            converted_audio_path = str(self.audio_dir / f"converted_{temp_uuid}.wav")

            # Step 1: Extract audio using MoviePy
            logger.info(f"Extracting audio from video: {video_path}")

            # Ensure the path is properly formatted for moviepy
            normalized_path = os.path.abspath(video_path).replace('\\', '/')

            video_clip = None
            audio_clip = None

            try:
                video_clip = VideoFileClip(normalized_path)
                if video_clip is None:
                    logger.error(f"Video clip could not be loaded from path: {normalized_path}")
                    return None

                audio_clip = video_clip.audio
                if audio_clip is None:
                    logger.error(f"No audio track found in video: {normalized_path}")
                    return None

                audio_clip.write_audiofile(temp_audio_path)
            finally:
                # Ensure resources are cleaned up even if there's an exception
                if audio_clip:
                    try:
                        audio_clip.close()
                    except:
                        pass  # Ignore errors when closing
                if video_clip:
                    try:
                        video_clip.close()
                    except:
                        pass  # Ignore errors when closing

            logger.info(f"Original audio extracted: {temp_audio_path}")

            # Force garbage collection and delay to ensure file is released
            gc.collect()
            time.sleep(1.0)

            # Check if the temp file was created and has content
            if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
                logger.error("Failed to extract audio from video")
                return None

            # Step 2: Use pydub to convert to Whisper-compatible format
            logger.info("Converting audio with pydub for Whisper compatibility...")
            audio = AudioSegment.from_wav(temp_audio_path)

            # Convert to mono, 16kHz for better Whisper compatibility
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(16000)
            audio.export(converted_audio_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])

            logger.info(f"Audio converted for Whisper: {converted_audio_path}")

            # Clean up the temporary original audio file
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)

            # Extra delay to ensure file is completely written
            time.sleep(0.5)

            # Verify the converted file exists and has content
            if os.path.exists(converted_audio_path) and os.path.getsize(converted_audio_path) > 0:
                return converted_audio_path
            else:
                logger.error("Converted audio file is missing or empty")
                return None

        except ImportError as e:
            logger.error(f"Required library not available: {e}")
            logger.info("Please install required libraries: pip install moviepy pydub")
            return None
        except Exception as e:
            logger.error(f"Error converting video to audio: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return None
    
    def transcribe_audio(self, audio_path: str) -> Optional[str]:
        """
        Transcribe audio using Whisper

        Args:
            audio_path: Path to the audio file to transcribe

        Returns:
            Transcription text, or None if transcription failed
        """
        try:
            import whisper
            import gc
            import time

            if not os.path.exists(audio_path):
                logger.error(f"Audio file does not exist: {audio_path}")
                return None

            # Load Whisper model
            logger.info("Loading Whisper model...")
            model = whisper.load_model("base")  # Use 'base' for faster processing

            # Add a small delay to ensure file is ready
            time.sleep(0.2)

            logger.info(f"Transcribing audio: {audio_path}")
            # Perform transcription
            result = model.transcribe(audio_path, verbose=False)

            transcription = result.get("text", "")

            if transcription:
                logger.info(f"Transcription completed. Length: {len(transcription)} characters")
                return transcription
            else:
                logger.warning("Transcription returned empty text")
                return None

        except ImportError as e:
            logger.error(f"Whisper library not available: {e}")
            logger.info("Please install Whisper: pip install openai-whisper")
            return None
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return None

    def process_video_for_transcription(self, video_path: str) -> Optional[str]:
        """
        Complete pipeline: convert video to audio and transcribe

        Args:
            video_path: Path to the input video file

        Returns:
            Transcription text, or None if the process failed
        """
        try:
            logger.info(f"Starting video transcription pipeline for: {video_path}")

            # Check if video file exists before proceeding
            if not os.path.exists(video_path):
                logger.error(f"Video file does not exist: {video_path}")
                return None

            # Extract video duration
            duration = self.get_video_duration(video_path)
            logger.info(f"Video duration: {duration} seconds")

            # Step 1: Convert video to audio
            audio_path = self.convert_video_to_audio(video_path)
            if not audio_path:
                logger.error("Failed to convert video to audio")
                return duration if duration else None  # Return duration if available, even if transcription fails

            # Step 2: Transcribe the audio
            transcription = self.transcribe_audio(audio_path)

            # Clean up the converted audio file after transcription
            if audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                    logger.info(f"Cleaned up temporary audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Could not clean up temporary file {audio_path}: {e}")

            if transcription:
                logger.info("✅ Video transcription pipeline completed successfully!")
                return transcription
            else:
                logger.error("Transcription was unsuccessful")
                # Still return the duration if transcription failed
                return None

        except Exception as e:
            logger.error(f"Error in video transcription pipeline: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return None

    def get_video_duration(self, video_path: str) -> Optional[float]:
        """
        Get the duration of a video file.

        Args:
            video_path: Path to the video file

        Returns:
            Duration in seconds, or None if failed to get duration
        """
        try:
            from moviepy.editor import VideoFileClip  # Updated import for newer versions
        except ImportError:
            try:
                from moviepy import VideoFileClip  # Fallback for older versions
            except ImportError:
                logger.error("MoviePy library not available for duration extraction")
                return None

        try:
            normalized_path = os.path.abspath(video_path).replace('\\', '/')
            video_clip = VideoFileClip(normalized_path)
            duration = video_clip.duration if video_clip.duration else 0
            video_clip.close()
            return duration
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            try:
                # Try to close video clip just in case
                if 'video_clip' in locals():
                    video_clip.close()
            except:
                pass
            return None


# Example usage
if __name__ == "__main__":
    processor = AudioProcessor()
    
    # Look for video files in the current directory
    video_files = []
    for file in os.listdir("."):
        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv', '.webm')):
            video_files.append(file)
    
    if video_files:
        test_video = video_files[0]
        logger.info(f"Found video file: {test_video}")
        transcription = processor.process_video_for_transcription(test_video)
        
        if transcription:
            logger.info(f"Transcription result (first 500 chars):\n{transcription[:500]}...")
        else:
            logger.error("Failed to process video for transcription")
    else:
        logger.info("No video files found in the current directory for testing")