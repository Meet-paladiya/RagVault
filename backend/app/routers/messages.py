"""
Messages router: send questions (with SSE streaming) and retrieve history.
POST /chats/{chat_id}/messages  → RAG query, returns StreamingResponse or MessageResponse
GET  /chats/{chat_id}/messages  → full message history
"""
import json
import logging
import asyncio
import re
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate, MessageListResponse, MessageResponse
from app.services.rag_service import run_rag, stream_rag
from app.services.document_readiness import ensure_documents_ready
from app.services.llm_gate import ollama_generation_gate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["Messages"])

_AUTO_TITLE_VALUES = {"New Chat", "New Knowledge Space"}


def _clean_generated_title(value: str) -> str:
    title = re.sub(r"[\"'`\n\r]", "", value).strip()
    title = re.sub(r"^(title|chat title)\s*:\s*", "", title, flags=re.IGNORECASE)
    return title[:80].strip(" .:-") or "New Chat"


async def _auto_title_chat(chat_id: str, question: str, answer: str) -> None:
    """Generate a short first-conversation title without delaying the answer stream."""
    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from langchain_community.llms import Ollama

    prompt = f"""Create a concise title for this study chat using the question and answer below.
Return only the title, 2 to 6 words, with no quotes or punctuation.
Question: {question[:800]}
Answer: {answer[:1200]}
Title:"""
    try:
        cfg = get_settings()
        llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model, temperature=0.0)
        async with ollama_generation_gate:
            raw_title = await asyncio.wait_for(asyncio.to_thread(llm.invoke, prompt), timeout=8.0)
        title = _clean_generated_title(str(raw_title))
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Chat).where(Chat.id == _to_uuid(chat_id)))
            chat = result.scalar_one_or_none()
            if chat and chat.title in _AUTO_TITLE_VALUES:
                chat.title = title
                await session.commit()
                logger.info("[CHATS] Generated title '%s' for chat %s", title, chat_id)
    except Exception as exc:
        logger.warning("[CHATS] Automatic title generation failed: %s", exc)


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


async def _load_chat_history(chat_id: str, db: AsyncSession, limit: int = 20) -> list[dict]:
    cid = _to_uuid(chat_id)
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == cid)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    # Return in chronological order
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


async def _save_messages(
    chat_id: str,
    user_content: str,
    assistant_content: str,
    citations: list[dict],
    user_asked_at: datetime | None = None,
) -> None:
    """Persist user question and assistant answer to PostgreSQL using a fresh DB session."""
    from app.database import AsyncSessionLocal

    cid = _to_uuid(chat_id)
    asked_time = user_asked_at or datetime.utcnow()
    completed_time = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        try:
            chat = (await session.execute(select(Chat).where(Chat.id == cid))).scalar_one_or_none()
            if chat is not None:
                chat.updated_at = datetime.utcnow()

            user_msg = Message(
                id=uuid4(),
                chat_id=cid,
                role="user",
                content=user_content,
                citations=None,
                created_at=asked_time,
            )
            assistant_msg = Message(
                id=uuid4(),
                chat_id=cid,
                role="assistant",
                content=assistant_content,
                citations=citations,
                created_at=completed_time,
            )
            session.add(user_msg)
            session.add(assistant_msg)
            await session.commit()
            logger.info("[MESSAGES] Saved user question (%s) and assistant answer (%s) for chat %s", asked_time, completed_time, chat_id)
        except Exception as exc:
            logger.error("[MESSAGES] Failed to save messages to DB: %s", exc)


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
      data: {"token": "..."}\\n\\n        → partial answer token
      data: {"citations": [...]}\\n\\n    → citation metadata
      data: [DONE]\\n\\n                 → stream end
    """
    chat = await _verify_chat_ownership(chat_id, current_user, db)
    await ensure_documents_ready(chat_id, db)
    chat_history = await _load_chat_history(chat_id, db)
    should_auto_title = not chat_history and chat.title in _AUTO_TITLE_VALUES
    asked_at = datetime.utcnow()

    if payload.stream:
        # ── Streaming path ────────────────────────────────────────────────────
        async def event_generator():
            full_answer_parts: list[str] = []
            citations: list[dict] = []

            async for chunk in stream_rag(payload.content, chat_id, chat_history):
                if chunk == "data: [DONE]\n\n":
                    # Guarantee DB commit completes BEFORE sending [DONE] signal to frontend
                    full_answer = "".join(full_answer_parts)
                    if full_answer:
                        await _save_messages(chat_id, payload.content, full_answer, citations, asked_at)
                        if should_auto_title:
                            asyncio.create_task(_auto_title_chat(chat_id, payload.content, full_answer))
                    yield "data: [DONE]\n\n"
                elif chunk.startswith("data: "):
                    raw_data = chunk.removeprefix("data: ").strip()
                    try:
                        parsed = json.loads(raw_data)
                        if isinstance(parsed, dict):
                            if "token" in parsed:
                                full_answer_parts.append(str(parsed["token"]))
                            elif "citations" in parsed:
                                citations = parsed["citations"]
                        else:
                            full_answer_parts.append(str(parsed))
                    except json.JSONDecodeError:
                        if raw_data.startswith("__citations__:"):
                            try:
                                citations = json.loads(raw_data.removeprefix("__citations__:").strip())
                            except Exception:
                                pass
                        elif raw_data:
                            full_answer_parts.append(raw_data)
                    yield chunk
                else:
                    yield chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # ── Non-streaming path ────────────────────────────────────────────────
        result = await run_rag(payload.content, chat_id, chat_history)
        await _save_messages(
            chat_id, payload.content, result["answer"], result["citations"], asked_at
        )
        if should_auto_title:
            asyncio.create_task(_auto_title_chat(chat_id, payload.content, result["answer"]))
        # Return the assistant message
        cid = _to_uuid(chat_id)
        db_result = await db.execute(
            select(Message)
            .where(Message.chat_id == cid, Message.role == "assistant")
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
    cid = _to_uuid(chat_id)
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == cid)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    msgs = result.scalars().all()
    return MessageListResponse(messages=[MessageResponse.model_validate(m) for m in msgs])


@router.delete("/{chat_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear all chat messages for a knowledge space without deleting documents, vector collections, notes, or quizzes."""
    await _verify_chat_ownership(chat_id, current_user, db)
    cid = _to_uuid(chat_id)
    await db.execute(delete(Message).where(Message.chat_id == cid))
    await db.commit()


@router.delete("/{chat_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_single_message(
    chat_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a single chat message by ID."""
    await _verify_chat_ownership(chat_id, current_user, db)
    cid = _to_uuid(chat_id)
    mid = _to_uuid(message_id)
    await db.execute(delete(Message).where(Message.chat_id == cid, Message.id == mid))
    await db.commit()
