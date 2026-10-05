from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class MemoryCategory(StrEnum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    PROFILE = "PROFILE"
    TASK = "TASK"
    CONTEXT = "CONTEXT"
    TEMPORARY = "TEMPORARY"


class MemoryRecord(BaseModel):
    memory_id: int | None = None
    user_id: str
    category: MemoryCategory
    content: str
    source_conversation_id: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
