"""Checks shared by generation endpoints before using the vector index."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def ensure_documents_ready(chat_id: str, db: AsyncSession) -> None:
    cid = UUID(str(chat_id))
    result = await db.execute(
        select(Document.status).where(Document.chat_id == cid)
    )
    statuses = [row[0] for row in result.all()]
    if any(document_status == "processing" for document_status in statuses):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document is still being processed. Please wait until all uploads are ready.",
        )
    if not statuses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents are uploaded in this chat. Open the chat where you uploaded the PDF.",
        )
    if statuses and not any(document_status == "processed" for document_status in statuses):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded documents could not be indexed. Please upload the PDF again.",
        )