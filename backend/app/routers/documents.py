"""
Documents router: file upload, status polling, and deletion.
Only PPTX, PDF, video, and audio files are accepted — everything else is rejected with 422.
Ingestion runs as a FastAPI BackgroundTask to avoid blocking the HTTP response.
"""
import logging
import os
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.ingestion_service import _validate_extension, ingest_document
from app.utils.chroma_client import delete_document_chunks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["Documents"])

# 2 GB upload limit
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024


def _to_uuid(val: str | UUID) -> UUID:
    return UUID(str(val)) if not isinstance(val, UUID) else val


async def _verify_chat_ownership(chat_id: str, user: User, db: AsyncSession) -> Chat:
    cid = _to_uuid(chat_id)
    result = await db.execute(select(Chat).where(Chat.id == cid))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if str(chat.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Access denied.")
    return chat


async def _background_ingest(
    chat_id: str,
    file_path: str,
    filename: str,
    document_id: str,
    db_url: str,
) -> None:
    """
    Background task entry point.
    Creates its own DB session since BackgroundTasks run outside the request lifecycle.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import get_settings

    cfg = get_settings()
    engine = create_async_engine(cfg.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        try:
            await ingest_document(
                db=session,
                chat_id=chat_id,
                file_path=file_path,
                filename=filename,
                document_id=document_id,
            )
        except Exception as exc:
            logger.exception("[INGEST:BG] Background ingestion failed for %s (%s): %s", filename, document_id, exc)
        finally:
            await engine.dispose()


@router.post(
    "/{chat_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    chat_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Upload and ingest a document into a knowledge space.

    - Validates file type (PDF, PPTX, TXT, MD, DOCX, Video, Audio).
    - Streams file to temporary storage.
    - Creates Document record in 'processing' status.
    - Dispatches ingestion pipeline as a background task.
    - Returns 202 Accepted immediately with the Document record.
    """
    await _verify_chat_ownership(chat_id, current_user, db)

    # Validate file extension
    try:
        ext = _validate_extension(file.filename or "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    from app.config import get_settings
    cfg = get_settings()

    # Save to temp directory
    doc_id = uuid4()
    temp_filename = f"{doc_id}{ext}"
    os.makedirs(cfg.upload_temp_dir, exist_ok=True)
    temp_path = os.path.join(cfg.upload_temp_dir, temp_filename)

    file_size = 0
    async with aiofiles.open(temp_path, "wb") as out_file:
        while content := await file.read(1024 * 1024):  # 1MB chunks
            file_size += len(content)
            if file_size > MAX_FILE_SIZE:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds maximum allowed limit (2GB).",
                )
            await out_file.write(content)

    cid = _to_uuid(chat_id)
    # Create Document record in DB
    doc = Document(
        id=doc_id,
        chat_id=cid,
        filename=file.filename,
        file_type=ext.lstrip("."),
        chroma_collection=f"chat_{str(cid).replace('-', '_')}",
        status="processing",
        total_pages=0,
        total_chunks=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Launch background ingestion
    background_tasks.add_task(
        _background_ingest,
        chat_id=chat_id,
        file_path=temp_path,
        filename=file.filename,
        document_id=str(doc_id),
        db_url=cfg.database_url,
    )

    return DocumentResponse.model_validate(doc)


@router.get("/{chat_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List all documents in a knowledge space with their processing status."""
    await _verify_chat_ownership(chat_id, current_user, db)
    cid = _to_uuid(chat_id)
    result = await db.execute(
        select(Document).where(Document.chat_id == cid).order_by(Document.upload_time.desc())
    )
    docs = result.scalars().all()
    return DocumentListResponse(documents=[DocumentResponse.model_validate(d) for d in docs])


@router.delete("/{chat_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    chat_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document and remove its chunks from ChromaDB."""
    await _verify_chat_ownership(chat_id, current_user, db)
    cid = _to_uuid(chat_id)
    doc_uuid = _to_uuid(doc_id)

    result = await db.execute(
        select(Document).where(Document.id == doc_uuid, Document.chat_id == cid)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    delete_document_chunks(chat_id, doc_id)
    await db.delete(doc)
    await db.commit()
