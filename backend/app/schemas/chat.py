from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import List

class ChatCreate(BaseModel):
    title: str

class ChatResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ChatListResponse(BaseModel):
    chats: List[ChatResponse]
