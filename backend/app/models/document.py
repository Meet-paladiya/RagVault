from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import CheckConstraint
import uuid
from datetime import datetime
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    total_pages = Column(Integer, nullable=True)
    total_chunks = Column(Integer, nullable=True)
    chroma_collection = Column(String, nullable=False)
    status = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(status.in_(['processing', 'processed', 'failed']), name='status_check'),
    )

    chat = relationship("Chat", back_populates="documents")
