"""
Chats router: CRUD for knowledge spaces + clear-knowledge action.
All routes require authentication. Ownership is verified on every operation.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.user import User
from app.schemas.chat import ChatCreate, ChatListResponse, ChatResponse
from app.utils.chroma_client import delete_collection

router = APIRouter(prefix="/chats", tags=["Chats"])


async def _get_owned_chat(chat_id: str, user: User, db: AsyncSession) -> Chat:
    """Helper: fetch a chat by ID and verify it belongs to the current user."""
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    if str(chat.user_id) != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return chat


@router.get("", response_model=ChatListResponse)
async def list_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatListResponse:
    """Return all knowledge spaces owned by the authenticated user."""
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
    )
    chats = result.scalars().all()
    return ChatListResponse(chats=[ChatResponse.model_validate(c) for c in chats])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Create a new knowledge space."""
    chat = Chat(
        id=uuid4(),
        user_id=current_user.id,
        title=payload.title,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return ChatResponse.model_validate(chat)


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Get a single knowledge space by ID."""
    chat = await _get_owned_chat(chat_id, current_user, db)
    return ChatResponse.model_validate(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a chat and all its associated ChromaDB vectors."""
    chat = await _get_owned_chat(chat_id, current_user, db)
    delete_collection(chat_id)  # wipe vectors
    await db.delete(chat)
    await db.commit()


@router.post("/{chat_id}/clear-knowledge", status_code=status.HTTP_200_OK)
async def clear_knowledge(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Explicitly wipe all ChromaDB vectors for this chat.
    Documents metadata in PostgreSQL is preserved.
    This is a destructive action — the user must confirm in the UI.
    """
    await _get_owned_chat(chat_id, current_user, db)
    delete_collection(chat_id)
    return {"message": "Knowledge cleared. All vector embeddings have been deleted.", "chat_id": chat_id}
