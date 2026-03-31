from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

# User Schemas
class UserRegister(BaseModel):
    email: EmailStr
    username: str  # name field
    password: str
    role: Literal["FACULTY", "STUDENT"]

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    username: str  # name field
    email: EmailStr
    role: Literal["FACULTY", "STUDENT"]

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Course Schemas
class CourseCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)

class CourseOut(BaseModel):
    courseId: str
    name: str
    description: str
    invitationCode: str
    invitationLink: str
    createdAt: datetime
    status: str

class CourseJoinRequest(BaseModel):
    invitationCode: str

class CourseJoinResponse(BaseModel):
    enrollmentId: str
    courseId: str
    courseName: str
    role: str
    joinedAt: datetime

class CourseListResponse(BaseModel):
    courses: List[dict]
    pagination: dict

# Module Schemas
class ModuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)

class ModuleOut(BaseModel):
    moduleId: str
    courseId: str
    name: str
    description: str
    createdAt: datetime
    status: str

# Resource Schemas
class ResourceUploadResponse(BaseModel):
    resourceId: str
    moduleId: str
    title: str
    type: str
    status: str
    statusUrl: str
    estimatedProcessingTime: int

class ResourceStatusResponse(BaseModel):
    resourceId: str
    status: str
    progress: int
    currentStep: str
    estimatedTimeRemaining: int
    error: Optional[str]

class ResourceListResponse(BaseModel):
    resources: List[dict]
    pagination: dict

# Summary Schemas
class SummaryCreate(BaseModel):
    lengthType: Literal["BRIEF", "DETAILED", "COMPREHENSIVE"]
    focusAreas: Optional[List[str]] = []

class SummaryOut(BaseModel):
    summaryId: str
    videoId: str
    lengthType: str
    content: str
    wordCount: int
    version: int
    isPublished: bool
    createdAt: datetime

class PublishSummaryRequest(BaseModel):
    isPublished: bool

class PublishSummaryResponse(BaseModel):
    summaryId: str
    isPublished: bool
    publishedAt: Optional[datetime]
    version: int

# Quiz Schemas
class QuizQuestion(BaseModel):
    index: int
    type: Literal["MCQ", "SHORT_ANSWER"]
    question: str
    options: Optional[List[str]] = []  # for MCQ only
    correctAnswer: str
    explanation: str
    difficulty: str
    timestamp: Optional[int] = None

class QuizCreate(BaseModel):
    title: str
    questions: List[QuizQuestion]

class QuizListResponse(BaseModel):
    quizzes: List[dict]

class QuizAnswer(BaseModel):
    questionIndex: int
    answer: str

class QuizAttemptRequest(BaseModel):
    answers: List[QuizAnswer]
    timeSpentSeconds: Optional[int] = 0

class QuizFeedback(BaseModel):
    questionIndex: int
    isCorrect: bool
    explanation: str
    correctAnswer: str

class QuizAttemptResponse(BaseModel):
    attemptId: str
    score: int
    totalQuestions: int
    correctAnswers: int
    timeSpentSeconds: int
    feedback: List[QuizFeedback]

# RAG Schemas
class AddDocumentsRequest(BaseModel):
    documents: List[str]

class GenerateRagPromptRequest(BaseModel):
    query: str
    llm_prompt_template: str
    context_documents: Optional[List[str]] = None

class GenerateRagPromptResponse(BaseModel):
    rag_prompt: str

class ExportEmbeddingsResponse(BaseModel):
    message: str
    file_path: str

# Chat Schemas
class ChatMessage(BaseModel):
    sender: str  # "user", "llm", "system"
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatHistory(BaseModel):
    userId: str
    messages: List[ChatMessage] = []

class ChatHistoryOut(ChatHistory):
    id: str = Field(..., alias="_id")

# Module Chat Schemas
class ModuleChatRequest(BaseModel):
    message: str

class ModuleChatResponse(BaseModel):
    response: str
    moduleId: str
    query: str
    context_used: bool

class ModuleChatHistoryResponse(BaseModel):
    moduleId: str
    chatHistory: List[dict]  # List of chat entries with query, response, timestamp, role

# AI Chat Schemas
class AIChatRequest(BaseModel):
    message: str
    sessionId: Optional[str] = None

class AIChatResponse(BaseModel):
    response: str
    intent: str
    generatedContent: Optional[dict]
    sessionId: str
    suggestions: List[str]