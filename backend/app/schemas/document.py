from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import List, Optional

class DocumentResponse(BaseModel):
    id: UUID
    chat_id: UUID
    filename: str
    file_type: str
    upload_time: datetime
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    status: str

    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
