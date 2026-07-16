"""Pydantic schemas for the AI query feature."""
from pydantic import BaseModel


class AskRequest(BaseModel):
    """Request body for the POST /ask endpoint."""

    question: str
    context: dict | None = None


class AskResponse(BaseModel):
    """Response from the AI query layer."""

    answer: str
    model: str
    turns: int
