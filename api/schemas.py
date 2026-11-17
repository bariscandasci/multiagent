"""HTTP şemaları."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message boş olamaz")
        return cleaned


class ChatResponse(BaseModel):
    session_id: str
    department: str
    route: str
    reason: str
    mode: str
    tools_used: list[str]
    answer: str


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    llm_configured: bool
    provider: str
    model: str
    agents: list[AgentInfo]
