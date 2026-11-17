"""FastAPI uygulaması."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.catalog import AGENTS
from api.schemas import AgentInfo, ChatRequest, ChatResponse, HealthResponse
from config import get_settings
from memory.session import Orchestrator, get_orchestrator


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="Şirket İçi Çoklu Ajan",
        version="0.1.0",
        summary="Yönetici ajan, İK, finans ve operasyon departmanlarına yönlendirir.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    runner = orchestrator or get_orchestrator()

    @app.get("/", tags=["sistem"])
    def root() -> dict[str, str]:
        return {"service": "company-multi-agent", "docs": "/docs", "health": "/health"}

    @app.get("/health", response_model=HealthResponse, tags=["sistem"])
    def health() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            status="ok",
            llm_configured=settings.configured,
            provider=settings.provider,
            model=settings.model,
            agents=[AgentInfo(**agent) for agent in AGENTS],
        )

    @app.get("/agents", response_model=list[AgentInfo], tags=["sistem"])
    def agents() -> list[AgentInfo]:
        return [AgentInfo(**agent) for agent in AGENTS]

    @app.post("/chat", response_model=ChatResponse, tags=["sohbet"])
    def chat(payload: ChatRequest) -> ChatResponse:
        return ChatResponse(**runner.ask(payload.message, payload.session_id))

    return app


app = create_app()
