from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import List, Optional

class MessageCreate(BaseModel):
    content: str
    stream: bool = True

class Citation(BaseModel):
    source: str
    page: int

class MessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
