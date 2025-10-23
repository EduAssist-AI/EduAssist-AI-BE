from contextlib import asynccontextmanager
from http.client import HTTPException
from fastapi import FastAPI
from fastapi.params import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.rag.generator import load_rag_generator
from app.routes import auth, rag, chat, courses, modules, videos, video_status, summaries, quizzes, ai_chat, module_chat
from fastapi.middleware.cors import CORSMiddleware
from app.utils.llm_generator import LLMGenerator
from fastapi.openapi.utils import get_openapi


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing LLM and RAG generator at startup...")
    app.state.generator = LLMGenerator()
    app.state.rag_generator = load_rag_generator()
    print("LLM and RAG generator loaded successfully.")
    yield
    print("Shutting down...")


app = FastAPI(lifespan=lifespan)

# CORS (for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
app.include_router(chat.router, prefix="/chat", tags=["Chat History"])
app.include_router(courses.router, prefix="/api/v1/courses", tags=["Course Management"])
app.include_router(modules.router, prefix="/api/v1", tags=["Module Management"])
app.include_router(videos.router, prefix="/api/v1", tags=["Video Management"])
app.include_router(video_status.router, prefix="/api/v1", tags=["Video Status"])
app.include_router(summaries.router, prefix="/api/v1", tags=["AI Content Generation"])
app.include_router(quizzes.router, prefix="/api/v1", tags=["Quiz Management"])
app.include_router(ai_chat.router, prefix="/api/v1", tags=["AI Chat"])
app.include_router(module_chat.router, prefix="/api/v1", tags=["Module Chat"])

@app.get("/health")
async def health_check():
    return {"message": "EduAssist API is running!"}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Your API",
        version="1.0.0",
        description="API with Auth",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    # Apply globally (optional), or do it per-endpoint
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            openapi_schema["paths"][path][method]["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

security = HTTPBearer()
