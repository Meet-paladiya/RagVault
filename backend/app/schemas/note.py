from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class NoteCard(BaseModel):
    id: str
    topic: str
    summary: str
    key_points: List[str]
    source: Optional[str] = "Document"
    page: Optional[int] = 1
    tag: str = "Concept"  # Options: Concept | Definition | Formula | Takeaway | Summary

    model_config = ConfigDict(from_attributes=True)

class NotesResponse(BaseModel):
    id: UUID
    chat_id: UUID
    title: str
    cards: List[NoteCard]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
