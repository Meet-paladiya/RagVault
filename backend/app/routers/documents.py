"""
Documents router: file upload, status polling, and deletion.
Only PPTX, PDF, video, and audio files are accepted — everything else is rejected with 422.
Ingestion runs as a FastAPI BackgroundTask to avoid blocking the HTTP response.
"""
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

router = APIRouter(prefix="/chats", tags=["Documents"])

# 2 GB upload limit
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024


async def _verify_chat_ownership(chat_id: str, user: User, db: AsyncSession) -> Chat:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
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
        except Exception:
            pass  # Status already set to 'failed' inside ingest_document
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
    Upload a document to a knowledge space.
    Accepted: PDF, PPTX, MP4/MKV/MOV/AVI/WEBM, MP3/WAV/M4A/OGG/FLAC/AAC.
    Rejected: DOCX, images, and all other types.

    Returns 202 immediately; ingestion runs in the background.
    Poll GET /chats/{chat_id}/documents to check status.
    """
    await _verify_chat_ownership(chat_id, current_user, db)

    filename = file.filename or "upload"
    try:
        _validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    from app.config import get_settings

    cfg = get_settings()

    # Save to temp directory
    temp_dir = os.path.join(cfg.upload_temp_dir, chat_id)
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, filename)

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    ext = os.path.splitext(filename)[1].lower()
    document_id = uuid4()  # UUID object — matches UUID(as_uuid=True) column

    # Create document record with status='processing'
    doc = Document(
        id=document_id,
        chat_id=UUID(chat_id),
        filename=filename,
        file_type=ext,
        chroma_collection=f"chat_{chat_id.replace('-', '_')}",
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Kick off background ingestion
    from app.config import get_settings as gs
    background_tasks.add_task(
        _background_ingest,
        chat_id=chat_id,
        file_path=file_path,
        filename=filename,
        document_id=str(document_id),  # convert back to str for ingest pipeline
        db_url=gs().database_url,
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
    result = await db.execute(
        select(Document).where(Document.chat_id == chat_id).order_by(Document.upload_time.desc())
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

    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.chat_id == chat_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    delete_document_chunks(chat_id, doc_id)
    await db.delete(doc)
    await db.commit()
