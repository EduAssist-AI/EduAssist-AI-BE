from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.auth import get_current_user
from app.db.mongo import db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.get("/videos/{video_id}/quizzes", status_code=status.HTTP_200_OK)
async def get_quiz_list(video_id: str, current_user=Depends(get_current_user)):
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
    
    # Get all published quizzes for this video
    quizzes = []
    async for quiz in db["quizzes"].find({"video_id": ObjectId(video_id), "is_published": True}):
        quiz_data = {
            "quizId": str(quiz["_id"]),
            "title": quiz["title"],
            "questionCount": len(quiz.get("questions", [])),
            "isPublished": quiz["is_published"],
            "version": quiz.get("version", 1),
            "averageScore": quiz.get("average_score", 0),  # Placeholder
            "attemptCount": quiz.get("attempt_count", 0)   # Placeholder
        }
        quizzes.append(quiz_data)
    
    return {"quizzes": quizzes}

@router.post("/quizzes/{quiz_id}/attempts", status_code=status.HTTP_201_CREATED)
async def submit_quiz_attempt(quiz_id: str, request_data: dict, current_user=Depends(get_current_user)):
    quiz = await db["quizzes"].find_one({"_id": ObjectId(quiz_id)})
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found."
        )
    
    video = await db["videos"].find_one({"_id": quiz["video_id"]})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated video not found."
        )
    
    # Check if user has access (course enrolled student)
    is_enrolled = await db["enrollments"].find_one({
        "user_id": ObjectId(current_user["_id"]), 
        "course_id": video["course_id"]
    }) is not None
    
    if not is_enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
    
    # Validate answers
    provided_answers = request_data.get("answers", [])
    quiz_questions = quiz.get("questions", [])
    
    if len(provided_answers) != len(quiz_questions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected {len(quiz_questions)} answers, got {len(provided_answers)}."
        )
    
    # Grade the quiz
    correct_count = 0
    feedback = []
    
    for i, question in enumerate(quiz_questions):
        provided_answer = next((ans for ans in provided_answers if ans.get("questionIndex") == i), None)
        if provided_answer:
            correct_answer = question["correctAnswer"]
            user_answer = provided_answer["answer"]
            
            is_correct = str(user_answer).lower() == str(correct_answer).lower()
            if is_correct:
                correct_count += 1
            
            feedback.append({
                "questionIndex": i,
                "isCorrect": is_correct,
                "explanation": question.get("explanation", ""),
                "correctAnswer": correct_answer
            })
    
    total_questions = len(quiz_questions)
    score = int((correct_count / total_questions) * 100) if total_questions > 0 else 0
    
    # Create attempt record
    attempt_doc = {
        "quiz_id": ObjectId(quiz_id),
        "user_id": ObjectId(current_user["_id"]),
        "answers": provided_answers,
        "score": score,
        "feedback": feedback,
        "submitted_at": datetime.utcnow(),
        "time_spent_seconds": request_data.get("timeSpentSeconds", 0)
    }
    
    result = await db["quiz_attempts"].insert_one(attempt_doc)
    
    return {
        "attemptId": str(result.inserted_id),
        "score": score,
        "totalQuestions": total_questions,
        "correctAnswers": correct_count,
        "timeSpentSeconds": attempt_doc["time_spent_seconds"],
        "feedback": feedback
    }