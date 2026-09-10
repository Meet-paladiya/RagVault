"""Generate page-complete study notes and export them as readable PDFs."""
import asyncio
import json
import logging
import re
import textwrap
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from langchain_community.llms import Ollama
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.note import Note
from app.models.chat import Chat
from app.utils.chroma_client import get_or_create_collection
from app.services.llm_gate import ollama_generation_gate

logger = logging.getLogger(__name__)

_PAGE_SCHEMA_PROMPT = """[
  {
        "source": "filename.pdf",
        "page": 1,
        "topic": "Short page topic",
        "summary": "Complete but concise summary of this page.",
    "key_points": [
            "Important fact, definition, example, or conclusion",
            "Formula: write the exact formula and define its variables"
    ],
        "tag": "Summary"
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


def _build_page_summary_prompt(filename: str, pages: list[dict[str, Any]]) -> str:
    page_context = "\n\n".join(
        f"===== PAGE {page['page']} =====\n{page['text']}" for page in pages
    )
    page_numbers = ", ".join(str(page["page"]) for page in pages)
    return f"""You are an expert academic tutor creating exam-ready notes for "{filename}".

Rules:
- Return exactly one summary object for every page number in this batch: {page_numbers}.
- Summarize each page in 2 concise sentences (max 30 words total).
- Maximum 3 key points per card (max 12 words per bullet point).
- Copy every formula, equation, symbol, unit, and important relationship accurately. Prefix formula items with "Formula:".
- Use the exact page number shown in each PAGE marker and attribute source as "{filename}".
- Output ONLY valid JSON array -- no markdown fences, no conversational text before or after.
- Valid tags: "Concept", "Definition", "Formula", "Takeaway", "Summary".

JSON SCHEMA:
{_PAGE_SCHEMA_PROMPT}

DOCUMENT TEXT ({filename}):
{page_context}

JSON ARRAY:"""


def _parse_and_repair_json(text: str) -> list[dict[str, Any]]:
    """Extract and repair potentially truncated JSON arrays or object wrappers from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip()

    def _extract_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            # Check common wrapper keys
            for key in ["cards", "notes", "summaries", "pages", "data", "items"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            # If dict contains topic/summary/key_points directly, treat as single item list
            if "topic" in data or "summary" in data or "key_points" in data:
                return [data]
            # Fallback: check any value that is a list of dicts
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
        return []

    # Try 1: Direct JSON parse on cleaned text
    try:
        res = json.loads(text)
        extracted = _extract_list(res)
        if extracted:
            return extracted
    except Exception:
        pass

    # Try 2: Extract substring from first '[' or '{' to last ']' or '}'
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    raw = match.group(0) if match else text
    try:
        res = json.loads(raw)
        extracted = _extract_list(res)
        if extracted:
            return extracted
    except Exception:
        pass

    # Try 3: Truncated JSON repair (find last complete object '}')
    try:
        start = raw.find('[')
        if start != -1:
            sub = raw[start:]
            last_brace = sub.rfind('}')
            if last_brace != -1:
                repaired = sub[:last_brace + 1] + '\n]'
                res = json.loads(repaired)
                extracted = _extract_list(res)
                if extracted:
                    return extracted
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

            page_raw = raw.get("page", 1)
            try:
                page_num = int(page_raw) if str(page_raw).strip().isdigit() else 1
            except Exception:
                page_num = 1

            valid.append({
                "id": f"card_{uuid4().hex[:8]}",
                "topic": topic,
                "summary": summary if summary else "Overview of key concepts from material.",
                "key_points": key_points if key_points else ["Key study point from document."],
                "source": filename,
                "page": max(1, page_num),
                "tag": tag,
            })
        except Exception as exc:
            logger.warning("[NOTES] Card parse error: %s", exc)

    return valid


def _invoke_llm(llm: Ollama, prompt: str) -> str:
    return llm.invoke(prompt)


async def generate_notes(db: AsyncSession, chat_id: str) -> Note:
    """Generate one complete, formula-aware study summary for every extracted page."""
    from app.config import get_settings
    cfg = get_settings()

    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    # Load chat title
    chat_res = await db.execute(select(Chat).where(Chat.id == cid))
    chat = chat_res.scalar_one_or_none()
    chat_title = chat.title if chat else "Knowledge Space"

    file_buckets = _get_file_chunks(chat_id)
    if not file_buckets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found in this knowledge space. Please upload documents first.",
        )

    llm = Ollama(
        base_url=cfg.ollama_base_url,
        model=cfg.ollama_model,
        temperature=0.2,
        format="json",
        num_predict=600,
    )
    all_cards: list[dict[str, Any]] = []

    for filename, chunks in file_buckets.items():
        pages: dict[int, dict[str, Any]] = {}
        for chunk in sorted(chunks, key=lambda item: (int(item["page"]), int(item["chunk_index"]))):
            page_number = int(chunk["page"])
            page = pages.setdefault(page_number, {"page": page_number, "text": ""})
            page["text"] += f"\n{chunk['text']}"

        page_items = list(pages.values())
        # Keep prompts bounded while ensuring every page is processed.
        for start in range(0, len(page_items), 3):
            page_batch = page_items[start:start + 3]
            prompt = _build_page_summary_prompt(filename, page_batch)
            logger.info("[NOTES] Summarizing pages %s from %s", [p["page"] for p in page_batch], filename)
            try:
                async with ollama_generation_gate:
                    raw = await asyncio.to_thread(_invoke_llm, llm, prompt)
                parsed = _parse_and_repair_json(raw)
                all_cards.extend(_normalise_cards(parsed, filename))
            except Exception as exc:
                logger.warning("[NOTES] Page summary error for %s: %s", filename, exc)

            summarized_pages = {int(card["page"]) for card in all_cards if card["source"] == filename}
            for page in page_batch:
                if page["page"] not in summarized_pages:
                    all_cards.append({
                        "id": f"card_fb_{uuid4().hex[:8]}",
                        "topic": f"Page {page['page']} Summary",
                        "summary": page["text"][:1200].strip(),
                        "key_points": [line.strip() for line in page["text"].splitlines() if line.strip()][:8],
                        "source": filename,
                        "page": page["page"],
                        "tag": "Summary",
                    })

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
        chat_id=cid,
        title=f"AI Notes: {chat_title}",
        cards=all_cards,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    logger.info("[NOTES] Total page summaries generated: %d across %d files", len(all_cards), len(file_buckets))
    return note


def build_notes_pdf(note: Note) -> bytes:
    """Render the generated notes as a plain, searchable text PDF."""
    import fitz

    document = fitz.open()
    page = document.new_page()
    cursor_y = 54.0

    def add_text(text: str, size: float = 10.5, bold: bool = False) -> None:
        nonlocal page, cursor_y
        font = "hebo" if bold else "helv"
        for line in text.splitlines() or [""]:
            wrapped_lines = textwrap.wrap(line, width=105, break_long_words=False, break_on_hyphens=False) or [""]
            for wrapped_line in wrapped_lines:
                if cursor_y > 760:
                    page = document.new_page()
                    cursor_y = 54.0
                page.insert_text((54, cursor_y), wrapped_line, fontsize=size, fontname=font)
                cursor_y += size + 4

    add_text(note.title, 17, True)
    add_text("Complete page-by-page exam revision summary", 10)
    add_text("", 10)
    for card in note.cards or []:
        add_text(f"{card.get('source', 'Document')} - Page {card.get('page', 1)}", 11, True)
        add_text(str(card.get("topic", "Page Summary")), 12, True)
        add_text(str(card.get("summary", "")), 10.5)
        for point in card.get("key_points", []):
            add_text(f"- {point}", 10.5)
        add_text("", 10)

    return document.tobytes(garbage=4, deflate=True)


async def get_latest_notes(db: AsyncSession, chat_id: str | UUID) -> Note | None:
    """Retrieve the most recent generated notes for a chat."""
    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    result = await db.execute(
        select(Note)
        .where(Note.chat_id == cid, ~Note.title.like("Quiz Remedial Notes%"))
        .order_by(desc(Note.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def generate_remedial_quiz_notes(
    db: AsyncSession,
    chat_id: str | UUID,
    quiz_id: str | UUID | None = None,
) -> Note:
    """Generate targeted remedial study cards for missed questions from a submitted quiz."""
    from app.models.quiz import Quiz

    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    cfg = get_settings()

    if quiz_id:
        qid = UUID(str(quiz_id)) if not isinstance(quiz_id, UUID) else quiz_id
        q_res = await db.execute(select(Quiz).where(Quiz.id == qid, Quiz.chat_id == cid))
        quiz = q_res.scalar_one_or_none()
    else:
        q_res = await db.execute(
            select(Quiz)
            .where(Quiz.chat_id == cid, Quiz.score.isnot(None))
            .order_by(desc(Quiz.created_at))
            .limit(1)
        )
        quiz = q_res.scalar_one_or_none()

    if not quiz or not quiz.questions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed quiz found. Please complete a quiz first to generate remedial notes.",
        )

    # Extract wrong questions
    wrong_cards: list[dict[str, Any]] = []
    questions_data = quiz.questions if isinstance(quiz.questions, list) else []

    for i, q in enumerate(questions_data, start=1):
        if not isinstance(q, dict):
            continue
        user_ans_id = q.get("user_answer")
        correct_ans_id = q.get("correct_option_id") or q.get("answer")

        user_opt_str = q.get("user_answer_text")
        correct_opt_str = q.get("correct_answer_text")

        opts = q.get("options", [])
        if not user_opt_str and opts:
            for opt in opts:
                if isinstance(opt, dict) and opt.get("id") == user_ans_id:
                    user_opt_str = str(opt.get("text", "")).strip()
            if not user_opt_str and isinstance(user_ans_id, int) and 0 <= user_ans_id < len(opts):
                user_opt_str = str(opts[user_ans_id])
            if not user_opt_str:
                user_opt_str = "Not Answered"

        if not correct_opt_str and opts:
            for opt in opts:
                if isinstance(opt, dict) and opt.get("id") == correct_ans_id:
                    correct_opt_str = str(opt.get("text", "")).strip()
            if not correct_opt_str and isinstance(correct_ans_id, int) and 0 <= correct_ans_id < len(opts):
                correct_opt_str = str(opts[correct_ans_id])
            if not correct_opt_str:
                correct_opt_str = "Unknown"

        is_wrong = (user_ans_id != correct_ans_id) if (user_ans_id is not None and correct_ans_id is not None) else True

        if is_wrong:
            q_text = q.get("question", f"Question {i}")
            explanation = q.get("explanation", "Review core concept from document.")

            wrong_cards.append({
                "id": f"remedial_{uuid4().hex[:6]}",
                "topic": f"Missed Question {i}: {q.get('topic', quiz.topic)}",
                "summary": f"Question: {q_text}\n• Your Answer: {user_opt_str}\n• Correct Answer: {correct_opt_str}\n\nExplanation: {explanation}",
                "key_points": [
                    f"Correct Answer: {correct_opt_str}",
                    f"Key Concept: {explanation[:120]}",
                ],
                "source": f"Quiz: {quiz.topic}",
                "page": i,
                "tag": "Remedial",
            })

    if not wrong_cards:
        wrong_cards.append({
            "id": f"remedial_perfect_{uuid4().hex[:6]}",
            "topic": f"Perfect Score! ({quiz.topic})",
            "summary": "Congratulations! You answered all questions correctly in your latest quiz.",
            "key_points": ["Excellent mastery of concepts!", "Keep reviewing core notes to retain knowledge."],
            "source": f"Quiz: {quiz.topic}",
            "page": 1,
            "tag": "Remedial",
        })

    note = Note(
        id=uuid4(),
        chat_id=cid,
        title=f"Quiz Remedial Notes: {quiz.topic}",
        cards=wrong_cards,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    logger.info("[REMEDIAL] Generated %d remedial cards for quiz %s", len(wrong_cards), quiz.id)
    return note


def build_remedial_notes_pdf(note: Note) -> bytes:
    """Render the generated remedial notes as a searchable text PDF."""
    import fitz

    document = fitz.open()
    page = document.new_page()
    cursor_y = 54.0

    def add_text(text: str, size: float = 10.5, bold: bool = False) -> None:
        nonlocal page, cursor_y
        font = "hebo" if bold else "helv"
        for line in text.splitlines() or [""]:
            wrapped_lines = textwrap.wrap(line, width=105, break_long_words=False, break_on_hyphens=False) or [""]
            for wrapped_line in wrapped_lines:
                if cursor_y > 760:
                    page = document.new_page()
                    cursor_y = 54.0
                page.insert_text((54, cursor_y), wrapped_line, fontsize=size, fontname=font)
                cursor_y += size + 4

    add_text(note.title, 16, True)
    add_text("Targeted Remedial Study Report for Missed Quiz Questions", 10)
    add_text("", 10)
    for card in note.cards or []:
        add_text(str(card.get("topic", "Missed Concept")), 12, True)
        add_text(str(card.get("summary", "")), 10.5)
        for point in card.get("key_points", []):
            add_text(f"- {point}", 10.5)
        add_text("", 10)

    return document.tobytes(garbage=4, deflate=True)


async def get_latest_remedial_notes(db: AsyncSession, chat_id: str | UUID) -> Note | None:
    """Retrieve the most recent remedial quiz notes for a chat."""
    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    result = await db.execute(
        select(Note)
        .where(Note.chat_id == cid, Note.title.like("Quiz Remedial Notes%"))
        .order_by(desc(Note.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
