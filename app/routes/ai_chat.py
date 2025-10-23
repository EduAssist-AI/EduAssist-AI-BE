from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/videos/{video_id}/chat", status_code=status.HTTP_200_OK)
async def ai_video_chat(video_id: str, request_data: dict, current_user=Depends(get_current_user)):
    video = await db["videos"].find_one({"_id": ObjectId(video_id)})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found."
        )
    
    # Check if user has access (course owner or enrolled student)
    course = await db["course_rooms"].find_one({"_id": video["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": video["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Extract message and session ID from the request
    message = request_data.get("message", "")
    session_id = request_data.get("sessionId", None)
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required."
        )
    
    # Process the message and generate response based on intent
    # This is a simplified implementation - in a real system, we would integrate with AI services
    lower_message = message.lower()
    
    # Determine intent
    if "summary" in lower_message or "summarize" in lower_message:
        intent = "GENERATE_SUMMARY"
        # Find any existing summary for this video or generate a basic one
        response_text = f"I've analyzed the video '{video['title']}' and can create a summary focusing on: {message}. This would typically generate a full summary based on the video content."
    elif "quiz" in lower_message or "question" in lower_message:
        intent = "GENERATE_QUIZ"
        response_text = f"I can help generate quiz questions based on the video '{video['title']}'. This would typically create quiz questions based on your request: {message}."
    else:
        intent = "GENERAL_QUERY"
        response_text = f"Thanks for your message about the video '{video['title']}'. I can help with summaries, quiz generation, and answering questions about the content. Based on your message '{message}', here's my response: This video covers educational content related to the course material."
    
    # Generate a session ID if not provided
    if not session_id:
        from uuid import uuid4
        session_id = str(uuid4())
    
    # Determine if any content was generated
    generated_content = None
    if intent == "GENERATE_SUMMARY":
        generated_content = {
            "contentType": "SUMMARY",
            "contentId": "temp-summary-id",  # In a real implementation, this would be an actual summary ID
            "preview": f"Summary created based on: {message}",
            "isPublished": False
        }
    elif intent == "GENERATE_QUIZ":
        generated_content = {
            "contentType": "QUIZ",
            "contentId": "temp-quiz-id",  # In a real implementation, this would be an actual quiz ID
            "preview": f"Quiz created based on: {message}",
            "isPublished": False
        }
    
    return {
        "response": response_text,
        "intent": intent,
        "generatedContent": generated_content,
        "sessionId": session_id,
        "suggestions": [
            "Make it more detailed",
            "Generate quiz questions",
            "Explain key concepts"
        ]
    }