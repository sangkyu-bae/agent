from fastapi import FastAPI
from pydantic import BaseModel

from src.application.chat_use_case import ChatUseCase
from src.infrastructure.llm_adapter import OpenAIAdapter


app = FastAPI(
    title="IDT API",
    description="FastAPI + LangGraph/LangChain RAG & Agent System",
    version="0.1.0",
)

llm_adapter = OpenAIAdapter()
chat_use_case = ChatUseCase(llm_adapter=llm_adapter)


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    response = await chat_use_case.execute(
        user_id=request.user_id,
        session_id=request.session_id,
        message=request.message,
    )
    return ChatResponse(
        session_id=request.session_id,
        response=response,
    )
