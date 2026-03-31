from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel
from typing import List, Optional
from app.utils.auth import get_current_user
from app.db.mongo import db
from app.rag.generator import load_rag_generator
from bson import ObjectId
from datetime import datetime
from app.schemas.user import UserOut
from app.schemas.modules import ModuleChatRequest, ModuleChatResponse, ModuleChatHistoryResponse, AllModulesChatHistoryResponse

async def get_content_from_resource_ids(resource_ids: list) -> list:
    """
    Retrieve content from specific resource IDs for RAG-based chat
    """
    from app.db.mongo import db
    from bson import ObjectId

    content_chunks = []

    # Convert string IDs to ObjectId and query the resources
    object_ids = [ObjectId(rid) for rid in resource_ids if ObjectId.is_valid(rid)]

    # Get transcripts for the specified resource IDs
    async for transcript in db["transcripts"].find({"resource_id": {"$in": object_ids}}):
        # Extract text from segments
        for segment in transcript.get("segments", []):
            text = segment.get("text", "")
            if text.strip():
                content_chunks.append(text)

    return content_chunks

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

        # Check if specific resource IDs are provided
        if request_data.resource_ids:
            # Retrieve content from specific resources
            relevant_chunks = await get_content_from_resource_ids(request_data.resource_ids)

            if relevant_chunks:
                # Use the content from specified resources
                context = "\n".join(relevant_chunks)
                # Check if the template has both placeholders, if not use default template
                template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

                # If template doesn't have placeholders, use default format with the custom instructions
                if "{context}" in template and "{query}" in template:
                    rag_prompt = template.format(context=context, query=query)
                else:
                    # Use default RAG format with the custom template as instructions
                    rag_prompt = f"{template}\n\nContext: {context}\n\nQuestion: {query}\n\nAnswer:"

                response = llm_generator.generate_response(rag_prompt)
                context_used = True
            else:
                # Fallback if no content found from specified resources
                module_context = f"Module: {module['name']}\nDescription: {module['description']}"
                template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

                if "{context}" in template and "{query}" in template:
                    rag_prompt = template.format(context=module_context, query=query)
                else:
                    rag_prompt = f"{template}\n\nContext: {module_context}\n\nQuestion: {query}\n\nAnswer:"

                response = llm_generator.generate_response(rag_prompt)
                context_used = False
        else:
            # Standard behavior: search for relevant content specifically from this module's videos
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

            if filtered_chunks:
                # Use RAG to get relevant content from module videos
                context = "\n".join(filtered_chunks)
                template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

                if "{context}" in template and "{query}" in template:
                    rag_prompt = template.format(context=context, query=query)
                else:
                    rag_prompt = f"{template}\n\nContext: {context}\n\nQuestion: {query}\n\nAnswer:"

                response = llm_generator.generate_response(rag_prompt)
                context_used = True
            else:
                # Fallback: use general module information
                module_context = f"Module: {module['name']}\nDescription: {module['description']}"
                template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

                if "{context}" in template and "{query}" in template:
                    rag_prompt = template.format(context=module_context, query=query)
                else:
                    rag_prompt = f"{template}\n\nContext: {module_context}\n\nQuestion: {query}\n\nAnswer:"

                response = llm_generator.generate_response(rag_prompt)
                context_used = False

    except Exception as e:
        # If RAG/LLM fails, return a meaningful response
        response = f"Based on module '{module['name']}', here is information related to your query about '{query}'. [Note: AI processing failed - {str(e)}]"
        context_used = False

    # Save the chat to module-specific chat history
    chat_entry = {
        "module_id": ObjectId(module_id),
        "user_id": ObjectId(current_user["id"]),
        "role": current_user["role"],
        "query": query,
        "response": response,
        "timestamp": datetime.utcnow(),
        "resource_ids_used": request_data.resource_ids if request_data.resource_ids else None  # Track which resources were used
    }

    await db["module_chats"].insert_one(chat_entry)

    return ModuleChatResponse(
        response=response,
        moduleId=module_id,
        query=query,
        context_used=context_used
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


class ResourceChatRequest(BaseModel):
    llm_prompt_template: str = "Context: {context}\n\nQuestion: {query}\n\nAnswer:"
    message: str
    resource_ids: List[str]  # Required list of resource IDs to use for RAG


class ResourceChatResponse(BaseModel):
    response: str
    query: str
    context_used: bool
    resource_ids_used: Optional[List[str]] = None


@router.post("/resources/chat", response_model=ResourceChatResponse, status_code=status.HTTP_200_OK)
async def resource_specific_chat(
    request: Request,
    request_data: ResourceChatRequest,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Chat endpoint that uses content from specific resource IDs for RAG
    """
    query = request_data.message
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required."
        )

    if not request_data.resource_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one resource ID is required."
        )

    # Validate that user has access to all resources by checking if they're enrolled in the associated courses
    resource_ids_validated = []
    for res_id in request_data.resource_ids:
        if not ObjectId.is_valid(res_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource ID: {res_id}"
            )

        resource = await db["resources"].find_one({"_id": ObjectId(res_id)})
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found: {res_id}"
            )

        # Check if user has access to the course containing this resource
        course = await db["course_rooms"].find_one({"_id": resource["course_id"]})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course for resource {res_id} not found."
            )

        is_owner = str(course["created_by"]) == current_user["id"]
        is_enrolled = await db["enrollments"].find_one({
            "user_id": ObjectId(current_user["id"]),
            "course_id": resource["course_id"]
        }) is not None

        if not (is_owner or is_enrolled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to resource {res_id}."
            )

        resource_ids_validated.append(res_id)

    # Use the application's actual RAG generator and LLM generator
    try:
        rag_generator = request.app.state.rag_generator
        llm_generator = request.app.state.generator

        # Retrieve content from specific resources
        relevant_chunks = await get_content_from_resource_ids(resource_ids_validated)

        if relevant_chunks:
            # Use the content from specified resources
            context = "\n".join(relevant_chunks)
            # Check if the template has both placeholders, if not use default template
            template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

            # If template doesn't have placeholders, use default format with the custom instructions
            if "{context}" in template and "{query}" in template:
                rag_prompt = template.format(context=context, query=query)
            else:
                # Use default RAG format with the custom template as instructions
                rag_prompt = f"{template}\n\nContext: {context}\n\nQuestion: {query}\n\nAnswer:"

            response = llm_generator.generate_response(rag_prompt)
            context_used = True
        else:
            # Fallback response when no content is found in specified resources
            # Use the template for the fallback response as well
            template = request_data.llm_prompt_template if request_data.llm_prompt_template else "Context: {context}\n\nQuestion: {query}\n\nAnswer:"

            if "{context}" in template and "{query}" in template:
                fallback_context = f"Selected resources did not contain content related to your query: {query}"
                rag_prompt = template.format(context=fallback_context, query=query)
                response = llm_generator.generate_response(rag_prompt)
            else:
                response = f"Based on the selected resources, I couldn't find specific content related to your query about '{query}'. Please check if the resources contain relevant information."

            context_used = False

    except Exception as e:
        # If RAG/LLM fails, return a meaningful response
        response = f"Based on the selected resources, here is information related to your query about '{query}'. [Note: AI processing failed - {str(e)}]"
        context_used = False

    # Save the chat to resource-specific chat history
    chat_entry = {
        "user_id": ObjectId(current_user["id"]),
        "role": current_user["role"],
        "query": query,
        "response": response,
        "timestamp": datetime.utcnow(),
        "resource_ids_used": resource_ids_validated
    }

    await db["resource_chats"].insert_one(chat_entry)

    return ResourceChatResponse(
        response=response,
        query=query,
        context_used=context_used,
        resource_ids_used=resource_ids_validated
    )