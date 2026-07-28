"""
Notes service: generates comprehensive card-based study notes for all uploaded documents via per-file batching and JSON repair.
"""
import asyncio
import json
import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from langchain_community.llms import Ollama
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.chat import Chat
from app.utils.chroma_client import get_or_create_collection

logger = logging.getLogger(__name__)

_CARD_SCHEMA_PROMPT = """[
  {
    "topic": "Core Concept or Important Topic Title",
    "summary": "Clear 2-sentence explanation of this key concept.",
    "key_points": [
      "Crucial detail or principle 1",
      "Important formula, definition, or rule 2",
      "Critical takeaway 3"
    ],
    "source": "filename.pdf",
    "page": 1,
    "tag": "Concept"
  }
]"""


def _get_file_chunks(chat_id: str) -> dict[str, list[dict[str, Any]]]:
    """Group all stored ChromaDB chunks by their source filename."""
    collection = get_or_create_collection(chat_id)
    try:
        results = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("ChromaDB get failed for notes: %s", exc)
        return {}

    docs = results.get("documents") or []
    metas = results.get("metadatas") or []
    if not docs:
        return {}

    file_buckets: dict[str, list[dict[str, Any]]] = {}
    for doc_text, meta in zip(docs, metas):
        source = meta.get("source", "Uploaded Document") if meta else "Uploaded Document"
        chunk_item = {
            "text": doc_text,
            "source": source,
            "page": meta.get("page", 1) if meta else 1,
            "chunk_index": meta.get("chunk_index", 0) if meta else 0,
        }
        file_buckets.setdefault(source, []).append(chunk_item)

    return file_buckets


def _build_per_file_prompt(filename: str, context: str, target_count: int = 4) -> str:
    return f"""You are an expert academic tutor. Create exactly {target_count} detailed study note cards from the document "{filename}".

Rules:
- Identify the MOST IMPORTANT concepts, formulas, definitions, and key takeaways in this text.
- Each card MUST explain a distinct key topic thoroughly.
- Attribute source as "{filename}".
- Output ONLY valid JSON array — no markdown fences, no conversational text before or after.
- Valid tags: "Concept", "Definition", "Formula", "Takeaway", "Summary".

JSON SCHEMA:
{_CARD_SCHEMA_PROMPT}

DOCUMENT TEXT ({filename}):
{context[:4500]}

JSON ARRAY:"""


def _parse_and_repair_json(text: str) -> list[dict[str, Any]]:
    """Extract and repair potentially truncated JSON arrays from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    raw = match.group(0) if match else text

    # Try 1: Direct JSON parse
    try:
        res = json.loads(raw)
        if isinstance(res, list):
            return res
    except Exception:
        pass

    # Try 2: Truncated JSON repair (find last complete object '}')
    try:
        start = raw.find('[')
        if start != -1:
            raw = raw[start:]
            last_brace = raw.rfind('}')
            if last_brace != -1:
                repaired = raw[:last_brace + 1] + '\n]'
                res = json.loads(repaired)
                if isinstance(res, list):
                    return res
    except Exception:
        pass

    return []


def _normalise_cards(cards_raw: list[dict[str, Any]], filename: str) -> list[dict[str, Any]]:
    valid = []
    allowed_tags = {"Concept", "Definition", "Formula", "Takeaway", "Summary"}

    for i, raw in enumerate(cards_raw):
        try:
            topic = str(raw.get("topic", f"Key Concept {i+1}")).strip()
            summary = str(raw.get("summary", "")).strip()
            kp_raw = raw.get("key_points", [])
            key_points = [str(p).strip() for p in kp_raw if str(p).strip()] if isinstance(kp_raw, list) else []

            if not summary and not key_points:
                continue

            tag = str(raw.get("tag", "Concept")).capitalize()
            if tag not in allowed_tags:
                tag = "Concept"

            valid.append({
                "id": f"card_{uuid4().hex[:8]}",
                "topic": topic,
                "summary": summary if summary else "Overview of key concepts from material.",
                "key_points": key_points if key_points else ["Key study point from document."],
                "source": str(raw.get("source", filename)),
                "page": int(raw.get("page", 1)) if str(raw.get("page", "")).isdigit() else 1,
                "tag": tag,
            })
        except Exception as exc:
            logger.warning("[NOTES] Card parse error: %s", exc)

    return valid


def _invoke_llm(llm: Ollama, prompt: str) -> str:
    return llm.invoke(prompt)


async def generate_notes(db: AsyncSession, chat_id: str) -> Note:
    """Generate comprehensive card-based study notes explaining all uploaded documents."""
    from app.config import get_settings
    cfg = get_settings()

    # Load chat title
    chat_res = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = chat_res.scalar_one_or_none()
    chat_title = chat.title if chat else "Knowledge Space"

    file_buckets = _get_file_chunks(chat_id)
    if not file_buckets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found in this knowledge space. Please upload documents first.",
        )

    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)
    all_cards: list[dict[str, Any]] = []

    num_files = len(file_buckets)
    target_per_file = max(3, 8 // num_files)

    for filename, chunks in file_buckets.items():
        # Combine text from this file
        context = "\n\n".join(
            f"[Page {c['page']}]\n{c['text']}" for c in chunks[:8]
        )
        prompt = _build_per_file_prompt(filename, context, target_count=target_per_file)

        logger.info("[NOTES] Generating %d cards for file: %s", target_per_file, filename)
        try:
            raw = await asyncio.to_thread(_invoke_llm, llm, prompt)
            parsed = _parse_and_repair_json(raw)
            normed = _normalise_cards(parsed, filename)
            all_cards.extend(normed)
        except Exception as exc:
            logger.warning("[NOTES] Card generation error for %s: %s", filename, exc)

    # Fallback if no cards parsed
    if not all_cards:
        for filename, chunks in file_buckets.items():
            for i, c in enumerate(chunks[:3], start=1):
                all_cards.append({
                    "id": f"card_fb_{uuid4().hex[:6]}",
                    "topic": f"Key Topic {i}: {filename}",
                    "summary": c["text"][:180] + "...",
                    "key_points": [c["text"][180:350] + "..."],
                    "source": filename,
                    "page": c["page"],
                    "tag": "Summary",
                })

    # Save to DB
    note = Note(
        id=uuid4(),
        chat_id=chat_id,
        title=f"AI Notes: {chat_title}",
        cards=all_cards,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    logger.info("[NOTES] Total generated study cards: %d across %d files", len(all_cards), num_files)
    return note


async def get_latest_notes(db: AsyncSession, chat_id: str) -> Note | None:
    """Retrieve the most recent generated notes for a chat."""
    result = await db.execute(
        select(Note)
        .where(Note.chat_id == chat_id)
        .order_by(desc(Note.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
