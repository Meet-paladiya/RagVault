from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class UserMemory(Base):
    __tablename__ = "user_memory"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    memory_text = Column(Text, nullable=False)
    source_chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memories")
    source_chat = relationship("Chat", back_populates="memories")
