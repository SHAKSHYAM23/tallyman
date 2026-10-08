from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    status: Literal["awaiting_input", "done", "gave_up", "error"]
    tool_results: dict = Field(default_factory=dict)