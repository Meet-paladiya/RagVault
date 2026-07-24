"""
Messages router: send questions (with SSE streaming) and retrieve history.
POST /chats/{chat_id}/messages  → RAG query, returns StreamingResponse or MessageResponse
GET  /chats/{chat_id}/messages  → full message history
"""
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate, MessageListResponse, MessageResponse
from app.services.rag_service import run_rag, stream_rag

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["Messages"])


async def _verify_chat_ownership(chat_id: str, user: User, db: AsyncSession) -> Chat:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if str(chat.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Access denied.")
    return chat


async def _load_chat_history(chat_id: str, db: AsyncSession, limit: int = 12) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    # Return in chronological order
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


async def _save_messages(
    db: AsyncSession,
    chat_id: str,
    user_content: str,
    assistant_content: str,
    citations: list[dict],
) -> None:
    """Persist user question and assistant answer to PostgreSQL."""
    user_msg = Message(
        id=uuid4(),
        chat_id=chat_id,
        role="user",
        content=user_content,
        citations=None,
    )
    assistant_msg = Message(
        id=uuid4(),
        chat_id=chat_id,
        role="assistant",
        content=assistant_content,
        citations=citations,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()


@router.post("/{chat_id}/messages", response_model=None)
async def send_message(
    chat_id: str,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | MessageResponse:
    """
    Ask a question in a knowledge space.

    If stream=True (default): returns an SSE stream of tokens.
    If stream=False: waits for full answer and returns a MessageResponse JSON.

    SSE format:
      data: <token>\\n\\n     → partial answer token
      data: __citations__:<json>\\n\\n  → citation metadata
      data: [DONE]\\n\\n      → stream end
    """
    await _verify_chat_ownership(chat_id, current_user, db)
    chat_history = await _load_chat_history(chat_id, db)

    if payload.stream:
        # ── Streaming path ────────────────────────────────────────────────────
        async def event_generator():
            full_answer_parts: list[str] = []
            citations: list[dict] = []

            async for chunk in stream_rag(payload.content, chat_id, chat_history):
                if chunk.startswith("data: __citations__:"):
                    raw = chunk.removeprefix("data: __citations__:").strip()
                    try:
                        citations = json.loads(raw)
                    except json.JSONDecodeError:
                        citations = []
                elif chunk == "data: [DONE]\n\n":
                    pass  # handled below
                else:
                    token = chunk.removeprefix("data: ").rstrip("\n")
                    full_answer_parts.append(token)
                yield chunk

            # Persist messages after stream completes
            full_answer = "".join(full_answer_parts)
            if full_answer:
                # Use a fresh session (outside request scope is fine here since we yield)
                await _save_messages(db, chat_id, payload.content, full_answer, citations)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # ── Non-streaming path ────────────────────────────────────────────────
        result = await run_rag(payload.content, chat_id, chat_history)
        await _save_messages(
            db, chat_id, payload.content, result["answer"], result["citations"]
        )
        # Return the assistant message
        db_result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        msg = db_result.scalar_one()
        return MessageResponse.model_validate(msg)


@router.get("/{chat_id}/messages", response_model=MessageListResponse)
async def get_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """Retrieve the full message history for a knowledge space."""
    await _verify_chat_ownership(chat_id, current_user, db)
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    msgs = result.scalars().all()
    return MessageListResponse(messages=[MessageResponse.model_validate(m) for m in msgs])
