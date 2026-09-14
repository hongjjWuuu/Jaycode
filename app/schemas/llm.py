from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryExtractionCandidate(BaseModel):
    memory_type: str
    memory_key: str
    content: str
    confidence: float = Field(ge=0, le=1)


class MemoryExtractionResponse(BaseModel):
    should_store: bool = False
    candidates: list[MemoryExtractionCandidate] = Field(default_factory=list)


class RerankResponse(BaseModel):
    ordered_chunk_ids: list[str] = Field(default_factory=list)
