from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List
from app.utils.auth import get_current_user
from app.db.mongo import chat_history_collection
from app.schemas.chat import ChatHistoryOut, ChatMessage, ChatHistory
from datetime import datetime

router = APIRouter()

@router.get("/history", response_model=ChatHistoryOut)
async def get_chat_history(
    current_user=Depends(get_current_user)
):
    """
    Retrieves the chat history for the current user.
    """
    chat_history = await chat_history_collection.find_one({"userId": current_user["id"]})
    if not chat_history:
        # If no chat history exists, create a new one
        new_chat_history = ChatHistory(userId=current_user["id"], messages=[])
        await chat_history_collection.insert_one(new_chat_history.dict(by_alias=True))
        chat_history = await chat_history_collection.find_one({"userId": current_user["id"]})
        if not chat_history:
            raise HTTPException(status_code=500, detail="Failed to create chat history.")

    # Convert ObjectId to string for Pydantic model
    chat_history["_id"] = str(chat_history["_id"])
    return ChatHistoryOut(**chat_history)

@router.post("/message", response_model=ChatMessage)
async def post_chat_message(
    request: Request,
    message: ChatMessage,
    current_user=Depends(get_current_user)
):
    """
    Sends a new message to the LLM with RAG and retrieves a response.
    """
    if message.sender != "user":
        raise HTTPException(status_code=400, detail="Sender must be 'user' for new messages.")

    rag_generator = request.app.state.rag_generator
    llm_generator = request.app.state.generator

    # Define a simple LLM prompt template
    llm_prompt_template = "Context: {context}\n\nQuestion: {query}\n\nAnswer:"
    
    # Retrieve relevant chunks based on the user's message
    relevant_chunks = rag_generator.retrieve_relevant_chunks(message.message)
    context = "\n".join(relevant_chunks) if relevant_chunks else "No specific context found."

    rag_prompt = llm_prompt_template.format(context=context, query=message.message)

    # Generate LLM response
    llm_response_content = llm_generator.generate_response(rag_prompt) # Assuming generate_response method

    llm_response = ChatMessage(
        sender="llm",
        message=llm_response_content,
        timestamp=datetime.utcnow()
    )

    # Update chat history
    chat_history = await chat_history_collection.find_one({"userId": current_user["id"]})
    if not chat_history:
        # This case should ideally be handled by get_chat_history creating it, but as a fallback
        new_chat_history = ChatHistory(userId=current_user["id"], messages=[message, llm_response])
        await chat_history_collection.insert_one(new_chat_history.dict(by_alias=True))
    else:
        await chat_history_collection.update_one(
            {"userId": current_user["id"]},
            {"$push": {"messages": {"$each": [message.dict(), llm_response.dict()]}}}
        )
    
    return llm_response