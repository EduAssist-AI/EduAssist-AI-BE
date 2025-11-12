from fastapi import APIRouter, HTTPException, Depends, status, Request
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.rag.generator import load_rag_generator
from bson import ObjectId
from datetime import datetime
from app.schemas.user import UserOut
from app.schemas.modules import ModuleChatRequest, ModuleChatResponse, ModuleChatHistoryResponse, AllModulesChatHistoryResponse

router = APIRouter()

@router.post("/modules/{module_id}/chat", response_model=ModuleChatResponse, status_code=status.HTTP_200_OK)
async def module_specific_chat(
    request: Request,  # Add request parameter to access app.state
    module_id: str, 
    request_data: ModuleChatRequest, 
    current_user: UserOut = Depends(get_current_user)
):
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
    
    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]), 
        "course_id": module["course_id"]
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    query = request_data.message
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required."
        )
    
    # Use the application's actual RAG generator and LLM generator
    try:
        rag_generator = request.app.state.rag_generator
        llm_generator = request.app.state.generator
        
        # Search for relevant content specifically from this module's videos
        relevant_chunks = rag_generator.search_video_content(query, video_id=None, top_k=5)
        
        # Filter to only include chunks from videos in this specific module
        module_video_ids = []
        async for video in db["videos"].find({"module_id": ObjectId(module_id)}):
            module_video_ids.append(str(video["_id"]))
        
        # Filter results by module's video IDs
        filtered_chunks = []
        for chunk_result in relevant_chunks:
            metadata = chunk_result.get("metadata", {})
            video_id = metadata.get("video_id")
            if video_id and video_id in module_video_ids:
                filtered_chunks.append(chunk_result["content"])
        
        # Define a simple LLM prompt template for educational content
        llm_prompt_template = "Context: {context}\n\nQuestion: {query}\n\nAnswer:"
        
        if filtered_chunks:
            # Use RAG to get relevant content from module videos
            context = "\n".join(filtered_chunks)
            rag_prompt = llm_prompt_template.format(context=context, query=query)
            response = llm_generator.generate_response(rag_prompt)
        else:
            # Fallback: use general module information
            module_context = f"Module: {module['name']}\nDescription: {module['description']}"
            rag_prompt = llm_prompt_template.format(context=module_context, query=query)
            response = llm_generator.generate_response(rag_prompt)
        
    except Exception as e:
        # If RAG/LLM fails, return a meaningful response
        response = f"Based on module '{module['name']}', here is information related to your query about '{query}'. [Note: AI processing failed - {str(e)}]"
    
    # Save the chat to module-specific chat history
    chat_entry = {
        "module_id": ObjectId(module_id),
        "user_id": ObjectId(current_user["id"]),
        "role": current_user["role"],
        "query": query,
        "response": response,
        "timestamp": datetime.utcnow()
    }
    
    await db["module_chats"].insert_one(chat_entry)
    
    return ModuleChatResponse(
        response=response,
        moduleId=module_id,
        query=query,
        context_used=len(filtered_chunks) > 0
    )

@router.get("/modules/{module_id}/chat/history", response_model=ModuleChatHistoryResponse, status_code=status.HTTP_200_OK)
async def get_module_chat_history(
    request: Request,  # Add request parameter to maintain consistency
    module_id: str, 
    current_user: UserOut = Depends(get_current_user)
):
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
    
    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]), 
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
    
    return ModuleChatHistoryResponse(
        moduleId=module_id,
        chatHistory=chat_history
    )

@router.get("/modules/chat/history", response_model=AllModulesChatHistoryResponse, status_code=status.HTTP_200_OK)
async def get_all_modules_chat_history(
    request: Request,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Get chat history from all modules the user has access to.
    This includes modules from courses where the user is either the owner or enrolled.
    """
    # Find all courses where user is owner or enrolled
    user_id = ObjectId(current_user["id"])
    
    # Find courses where user is the owner
    owned_courses = []
    async for course in db["course_rooms"].find({"created_by": user_id}):
        owned_courses.append(course["_id"])
    
    # Find courses where user is enrolled
    enrolled_course_ids = []
    async for enrollment in db["enrollments"].find({"user_id": user_id}):
        enrolled_course_ids.append(enrollment["course_id"])
    
    # Combine all course IDs the user has access to
    accessible_course_ids = list(set(owned_courses + enrolled_course_ids))
    
    if not accessible_course_ids:
        return AllModulesChatHistoryResponse(allModulesChatHistory=[])
    
    # Find all modules in these courses
    module_ids = []
    async for module in db["modules"].find({"course_id": {"$in": accessible_course_ids}}):
        module_ids.append(module["_id"])
    
    if not module_ids:
        return AllModulesChatHistoryResponse(allModulesChatHistory=[])
    
    # Get chat history for all accessible modules
    all_chat_history = []
    
    # Get all chat entries for these modules, sorted by timestamp
    async for chat in db["module_chats"].find({
        "module_id": {"$in": module_ids},
        "user_id": user_id  # Only get chats from the current user
    }).sort("timestamp", -1):
        # Get module information to include in the response
        module = await db["modules"].find_one({"_id": chat["module_id"]})
        
        chat_entry = {
            "moduleId": str(chat["module_id"]),
            "moduleName": module["name"] if module else "Unknown Module",
            "query": chat["query"],
            "response": chat["response"],
            "role": chat["role"],
            "timestamp": chat["timestamp"]
        }
        all_chat_history.append(chat_entry)
    
    return AllModulesChatHistoryResponse(
        allModulesChatHistory=all_chat_history
    )

@router.get("/courses/{course_id}/modules/chat/history", response_model=AllModulesChatHistoryResponse, status_code=status.HTTP_200_OK)
async def get_course_modules_chat_history(
    request: Request,
    course_id: str,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Get chat history from all modules in a specific course.
    Only accessible to course owners or enrolled students.
    """
    course_object_id = ObjectId(course_id)
    
    # Check if course exists
    course = await db["course_rooms"].find_one({"_id": course_object_id})
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found."
        )
    
    # Check if user has access to the course
    is_owner = str(course["created_by"]) == current_user["id"]
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["id"]), 
        "course_id": course_object_id
    }) is not None
    
    if not (is_owner or is_enrolled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Find all modules in this course
    module_ids = []
    async for module in db["modules"].find({"course_id": course_object_id}):
        module_ids.append(module["_id"])
    
    if not module_ids:
        return AllModulesChatHistoryResponse(allModulesChatHistory=[])
    
    # Get chat history for all modules in this course
    course_chat_history = []
    
    # Get all chat entries for these modules, sorted by timestamp
    async for chat in db["module_chats"].find({
        "module_id": {"$in": module_ids}
    }).sort("timestamp", -1):
        # Get module information to include in the response
        module = await db["modules"].find_one({"_id": chat["module_id"]})
        
        chat_entry = {
            "moduleId": str(chat["module_id"]),
            "moduleName": module["name"] if module else "Unknown Module",
            "query": chat["query"],
            "response": chat["response"],
            "role": chat["role"],
            "timestamp": chat["timestamp"]
        }
        course_chat_history.append(chat_entry)
    
    return AllModulesChatHistoryResponse(
        allModulesChatHistory=course_chat_history
    )