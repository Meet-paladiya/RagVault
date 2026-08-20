"""
Notes router: API endpoints for AI Notes generation and retrieval.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.user import User
from app.schemas.note import NotesResponse
from app.services.notes_service import generate_notes, get_latest_notes

router = APIRouter(prefix="/chats", tags=["Notes"])


def _to_uuid(val: str | UUID) -> UUID:
    """Helper to convert string or UUID to UUID object safely."""
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


@router.post("/{chat_id}/notes", response_model=NotesResponse, status_code=201)
async def create_notes(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotesResponse:
    """Generate structured AI note cards for all resources in a knowledge space."""
    await _verify_chat_ownership(chat_id, current_user, db)
    note = await generate_notes(db=db, chat_id=chat_id)
    return NotesResponse.model_validate(note)


@router.get("/{chat_id}/notes", response_model=Optional[NotesResponse])
async def fetch_notes(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[NotesResponse]:
    """Get the latest AI note cards for a knowledge space. Returns null if none generated yet."""
    await _verify_chat_ownership(chat_id, current_user, db)
    note = await get_latest_notes(db=db, chat_id=chat_id)
    if not note:
        return None
    return NotesResponse.model_validate(note)
