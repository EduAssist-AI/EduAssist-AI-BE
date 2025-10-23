from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.rag.generator import load_rag_generator
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/modules/{module_id}/chat", status_code=status.HTTP_200_OK)
async def module_specific_chat(module_id: str, request_data: dict, current_user=Depends(get_current_user)):
    # Check if module exists
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found."
        )
    
    # Check if user has access to the course containing this module
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": module["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    query = request_data.get("message", "")
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required."
        )
    
    # Retrieve module-specific content for RAG context
    # Get all videos, slides, and their summaries associated with this module
    videos = []
    async for video in db["videos"].find({"module_id": ObjectId(module_id), "published": True}):
        # Get associated summary if available
        summary = await db["summaries"].find_one({"video_id": video["_id"], "is_published": True})
        
        video_context = f"Video: {video['title']}"
        if summary:
            video_context += f"\nSummary: {summary['content']}"
        
        videos.append(video_context)
    
    # Create a RAG context from module materials
    module_context = f"Module: {module['name']}\nDescription: {module['description']}\n\n"
    module_context += "Materials:\n" + "\n".join(videos)
    
    # Use the application's RAG generator (accessed via app.state in the main app)
    # For now, we'll simulate the RAG response
    rag_prompt = f"Based on the following module content:\n\n{module_context}\n\nQuestion: {query}\n\nAnswer:"
    
    # In a real implementation, we would use app.state.rag_generator
    # For now, returning a simulated response
    response = f"Based on module '{module['name']}', here is information related to your query about '{query}'. This would be generated using RAG context from the module materials."
    
    # Save the chat to module-specific chat history
    chat_entry = {
        "module_id": ObjectId(module_id),
        "user_id": ObjectId(current_user["_id"]),
        "role": current_user["role"],
        "query": query,
        "response": response,
        "timestamp": datetime.utcnow()
    }
    
    await db["module_chats"].insert_one(chat_entry)
    
    return {
        "response": response,
        "moduleId": module_id,
        "query": query,
        "context_used": len(videos) > 0
    }

@router.get("/modules/{module_id}/chat/history", status_code=status.HTTP_200_OK)
async def get_module_chat_history(module_id: str, current_user=Depends(get_current_user)):
    # Check if module exists
    module = await db["modules"].find_one({"_id": ObjectId(module_id)})
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found."
        )
    
    # Check if user has access to the course containing this module
    course = await db["course_rooms"].find_one({"_id": module["course_id"]})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module course not found."
        )
    
    is_owner = str(course["created_by"]) == current_user["_id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": module["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Get chat history for this module
    chat_history = []
    async for chat in db["module_chats"].find({
        "module_id": ObjectId(module_id)
    }).sort("timestamp", -1).limit(50):  # Limit to last 50 messages
        chat_entry = {
            "query": chat["query"],
            "response": chat["response"],
            "role": chat["role"],
            "timestamp": chat["timestamp"]
        }
        chat_history.append(chat_entry)
    
    # Reverse to show oldest first
    chat_history.reverse()
    
    return {
        "moduleId": module_id,
        "chatHistory": chat_history
    }