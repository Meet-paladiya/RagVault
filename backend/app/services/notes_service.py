import asyncio
import io
import json
import logging
import re
import textwrap
import zipfile
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.note import Note
from app.models.chat import Chat
from app.utils.chroma_client import get_or_create_collection
from app.services.llm_gate import ollama_generation_gate

logger = logging.getLogger(__name__)

_SECTION_SCHEMA_PROMPT = """[
  {
    "chapter": "Chapter 6: Deep Generative Models",
    "topic": "Variational Autoencoders & Latent Distribution",
    "summary": "Dense 1-2 sentence overview capturing the core mathematical mechanisms and concepts.",
    "key_points": [
      "**Encoder-Decoder Mapping**: Maps inputs to latent distributions z ~ N(mu, sigma^2) using the reparameterization trick.",
      "**ELBO Loss**: Maximizes reconstruction probability while minimizing KL divergence: Formula: L = E[log p(x|z)] - D_KL(q(z|x)||p(z))"
    ],
    "tag": "Concept",
    "is_new_chapter": false
  }
]"""


def _sanitize_slide_text(text: str) -> str:
    """Filter out isolated numbers, slide matrix cells, presenter boilerplate, and OCR noise."""
    if not text:
        return ""
    lines = text.splitlines()
    clean_lines = []

    drop_patterns = [
        re.compile(r'^\s*(prepared\s+by|presented\s+by|assistant\s+professor|associate\s+professor|prof\.|professor|dr\.|department|scet|surat|university|college|faculty)\b', re.IGNORECASE),
        re.compile(r'^\s*(lecture\s+\d+|slide\s+\d+|chapter\s+\d+|module\s+\d+|page\s+\d+)\s*$', re.IGNORECASE),
        re.compile(r'^\s*[-+]?\d+(\.\d+)?\s*$'),  # Lone number / matrix value
        re.compile(r'^\s*[-+*=/_~^#\(\)\{\}\[\]\.,;:\'"|·•]+\s*$'),  # Lone symbols
        re.compile(r'^\s*\(?\s*([0-9xyz\s,+-]{1,10})\s*\)?\s*$', re.IGNORECASE),  # Coordinates like (x,y), (0,0)
        re.compile(r'^\s*[a-z]\s*$', re.IGNORECASE),  # Lone single character
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(pat.search(stripped) for pat in drop_patterns):
            continue
        cleaned = re.sub(r'^[·•\-\*]+\s*', '', stripped)
        cleaned = re.sub(r'[·•]{2,}', ' ', cleaned)
        cleaned = cleaned.replace('·', ' ').strip()
        if len(cleaned) >= 4 and any(c.isalpha() for c in cleaned):
            clean_lines.append(cleaned)

    cohesive_text = " ".join(clean_lines)
    cohesive_text = re.sub(r'\s+', ' ', cohesive_text).strip()
    return cohesive_text


def _clean_topic_title(topic: str) -> str:
    """Strip out page numbers, page ranges, symbols, and generic 'Summary' labels from topics."""
    if not topic:
        return "Core Concepts"
    # Remove leading/trailing middle dots, bullets, symbols
    cleaned = re.sub(r'^[•·\-\*—–:]+\s*', '', topic)
    cleaned = re.sub(r'[•·\-\*—–:]+\s*$', '', cleaned)
    # Remove ": Pages 1–4", ": Page 1", "(Pages 1-4)", "Pages 1-4"
    cleaned = re.sub(r'[:\-–—]?\s*\(?pages?\s*\d+([–\-]\d+)?\)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bpages?\s*\d+([–\-]\d+)?\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(summary|overview)\b', '', cleaned, flags=re.IGNORECASE).strip(' :-–—\t\r\n')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' :-–—\t\r\n')
    return cleaned if len(cleaned) >= 3 else (topic.strip() or "Core Concepts")


def _merge_points_for_brevity(points: list[str], max_points: int = 3) -> list[str]:
    """Merge and condense bullet points so total key points are concise (max 2-3 points)."""
    cleaned = [p.strip() for p in points if p and len(p.strip()) > 5]
    if not cleaned:
        return []
    if len(cleaned) <= max_points:
        return cleaned

    merged = []
    for i in range(0, len(cleaned), 2):
        if len(merged) >= max_points:
            if len(merged[-1]) < 180 and i < len(cleaned):
                merged[-1] += f" | {cleaned[i]}"
            break
        pair = cleaned[i:i+2]
        if len(pair) == 2:
            p1 = pair[0].rstrip('.')
            p2 = pair[1].lstrip('-• ')
            merged.append(f"{p1}; {p2}")
        else:
            merged.append(pair[0])
    return merged[:max_points]


def _detect_subtopic_heading(text: str) -> str | None:
    """Scan page text for subtopic headers (e.g. ## Topic, bold headings, capitalized sections)."""
    match = re.search(r'(?m)^#{2,4}\s+([A-Z][^\n\r]{3,60})', text[:1200])
    if match:
        return _clean_topic_title(match.group(1))
    lines = [line.strip() for line in text[:800].splitlines() if line.strip()]
    for line in lines:
        if 4 <= len(line) <= 60 and not re.match(r'(?i)^(page|chapter|module|\d+)', line):
            if any(c.isupper() for c in line) and not line.endswith('.'):
                clean = _clean_topic_title(line)
                if not re.search(r'(?i)\b(prepared|professor|department|scet)\b', clean):
                    return clean
    return None


def _detect_chapter_heading(text: str) -> str | None:
    """Scan leading lines of page text for chapter or major module headings."""
    pattern = r'(?im)^(?:#+\s*)?(?:chapter|module|unit|lecture|part|section)\s+([0-9ivxlcdm]+|[a-z]+)[:\s\-–—]+([^\n\r]{3,80})'
    match = re.search(pattern, text[:800])
    if match:
        return _clean_topic_title(match.group(0).strip('# \t\r\n'))
    short_pattern = r'(?im)^(?:#+\s*)?(chapter\s+[0-9ivxlcdm]+)\b'
    match_short = re.search(short_pattern, text[:400])
    if match_short:
        return match_short.group(1).title()
    return None


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


def _build_continuous_section_prompt(
    filename: str,
    pages: list[dict[str, Any]],
    current_chapter: str | None,
) -> str:
    page_context = "\n\n".join(
        f"===== SECTION PAGES {page['page']} =====\n{page['text']}" for page in pages
    )
    page_numbers = ", ".join(str(page["page"]) for page in pages)
    chapter_hint = f'Chapter context: "{current_chapter}".' if current_chapter else "Document start."

    return f"""You are an expert tutor creating a concise, high-yield 2-page exam revision summary for "{filename}".
{chapter_hint}

Content covering pages: {page_numbers}.

CRITICAL INSTRUCTIONS:
1. TOPIC: Conceptual subject title (e.g. "Image Enhancement & Spatial Filtering", "Derivative Operators & Edge Detection").
   - NEVER include page numbers or page ranges (e.g. "Pages 1-4") or the word "Summary".
2. CONCISE SUMMARY:
   - Provide a dense, high-yield 1-2 sentence overview synthesizing the core concepts across these pages.
3. MERGED KEY POINTS (EXACTLY 2-3 BULLETS):
   - Merge related points together.
   - Start each point with a bold keyword concept: "**Concept/Mechanism**: Brief explanation with formula if applicable".
4. OUTPUT:
   - ONLY a valid JSON array matching the schema below. Tag must be "Concept", "Definition", or "Formula".

JSON SCHEMA:
{_SECTION_SCHEMA_PROMPT}

DOCUMENT CONTENT ({filename}):
{page_context}

JSON ARRAY:"""


async def _call_llm_json(prompt: str) -> str:
    """Send prompt to local OpenAI-compatible / llama.cpp or Ollama LLM server."""
    cfg = get_settings()
    endpoints = [
        # 1. Primary OpenAI-compatible endpoint from settings (e.g. http://llm:8000/v1)
        (f"{cfg.llm_base_url.rstrip('/')}/chat/completions", {
            "model": cfg.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": False,
        }),
        # 2. Alternative direct port 8080 (llama.cpp server direct port)
        ("http://llm:8080/v1/chat/completions", {
            "model": cfg.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": False,
        }),
        # 3. Native Ollama API
        (f"{cfg.ollama_base_url.rstrip('/')}/api/generate", {
            "model": cfg.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }),
    ]

    for url, payload in endpoints:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if "choices" in data and data["choices"]:
                        msg = data["choices"][0].get("message", {}).get("content", "")
                        if msg and msg.strip():
                            return msg.strip()
                    if "response" in data and data["response"]:
                        return data["response"].strip()
        except Exception as exc:
            logger.debug("[NOTES] LLM call to %s failed: %s", url, exc)
            continue

    raise RuntimeError("All LLM endpoints failed")


def _generate_clean_fallback_card(
    page_batch: list[dict[str, Any]],
    filename: str,
    batch_idx: int,
    current_chapter: str | None,
) -> dict[str, Any]:
    """Synthesize a coherent, clean fallback card when LLM is unavailable."""
    batch_page_nums = [p["page"] for p in page_batch]
    p_start = batch_page_nums[0]
    p_end = batch_page_nums[-1]

    sanitized_pages = [_sanitize_slide_text(p["text"]) for p in page_batch]
    combined_clean = " ".join(t for t in sanitized_pages if t).strip()

    topic = None
    for p in page_batch:
        topic = _detect_subtopic_heading(p["text"])
        if topic:
            break
    if not topic:
        topic = _detect_chapter_heading(combined_clean) or f"Core Topic {batch_idx + 1}"
    topic = _clean_topic_title(topic)

    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', combined_clean)
    valid_sentences = [
        s.strip() for s in sentences
        if len(s.strip()) > 25 and not re.search(r'^\s*[-+]?\d+', s) and any(c.isalpha() for c in s)
    ]

    summary = ""
    if valid_sentences:
        summary = " ".join(valid_sentences[:2])
        if len(summary) > 280:
            summary = summary[:277] + "..."
    else:
        summary = f"Core theoretical and practical principles presented in pages {p_start} through {p_end}."

    key_points = []
    for s in valid_sentences[2:6]:
        words = s.split()
        if len(words) >= 4:
            lead = " ".join(words[:2]).strip(':,.-')
            rest = " ".join(words[2:])
            key_points.append(f"**{lead.title()}**: {rest}")
        if len(key_points) >= 2:
            break

    if not key_points:
        key_points = [
            f"**Key Mechanism**: Core concepts and methodologies outlined in {filename}.",
            "**Key Application**: Analytical methods and structural foundations for revision.",
        ]

    return {
        "id": f"card_clean_{uuid4().hex[:8]}",
        "chapter": _clean_topic_title(current_chapter) if current_chapter else "",
        "topic": topic,
        "summary": summary,
        "key_points": _merge_points_for_brevity(key_points, max_points=2),
        "source": filename,
        "page": p_start,
        "page_end": p_end,
        "is_new_chapter": (batch_idx == 0),
        "tag": "Concept",
    }


def _parse_and_repair_json(text: str) -> list[dict[str, Any]]:
    """Extract and repair potentially truncated JSON arrays or object wrappers from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip()

    def _extract_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ["cards", "notes", "summaries", "pages", "sections", "data", "items"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            if "topic" in data or "summary" in data or "key_points" in data:
                return [data]
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
        return []

    try:
        res = json.loads(text)
        extracted = _extract_list(res)
        if extracted:
            return extracted
    except Exception:
        pass

    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    raw = match.group(0) if match else text
    try:
        res = json.loads(raw)
        extracted = _extract_list(res)
        if extracted:
            return extracted
    except Exception:
        pass

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


def _normalise_cards(
    cards_raw: list[dict[str, Any]],
    filename: str,
    default_chapter: str = "General",
    fallback_pages: list[int] | None = None,
) -> list[dict[str, Any]]:
    valid = []
    allowed_tags = {"Concept", "Definition", "Formula", "Takeaway"}

    for i, raw in enumerate(cards_raw):
        try:
            raw_topic = str(raw.get("topic", f"Section {i+1}")).strip()
            topic = _clean_topic_title(raw_topic)
            summary = str(raw.get("summary", "")).strip()
            summary = re.sub(r'(?i)\bpages?\s*\d+([–\-]\d+)?\b', '', summary).strip()
            summary = _sanitize_slide_text(summary)

            kp_raw = raw.get("key_points", [])
            key_points_raw = [str(p).strip() for p in kp_raw if str(p).strip()] if isinstance(kp_raw, list) else []
            key_points = _merge_points_for_brevity(key_points_raw, max_points=3)

            if not summary and not key_points:
                continue

            tag = str(raw.get("tag", "Concept")).capitalize()
            if tag not in allowed_tags:
                tag = "Concept"

            p_start_raw = raw.get("page_start", raw.get("page", 1))
            try:
                page_start = int(p_start_raw) if str(p_start_raw).strip().isdigit() else (fallback_pages[0] if fallback_pages else 1)
            except Exception:
                page_start = fallback_pages[0] if fallback_pages else 1

            p_end_raw = raw.get("page_end", page_start)
            try:
                page_end = int(p_end_raw) if str(p_end_raw).strip().isdigit() else (fallback_pages[-1] if fallback_pages else page_start)
            except Exception:
                page_end = fallback_pages[-1] if fallback_pages else page_start

            raw_ch = str(raw.get("chapter", default_chapter)).strip() or default_chapter
            chapter = _clean_topic_title(raw_ch)
            if chapter.lower() in {"general", "summary", "overview", "chapter overview"}:
                chapter = ""

            is_new = bool(raw.get("is_new_chapter", False))

            valid.append({
                "id": f"card_{uuid4().hex[:8]}",
                "chapter": chapter,
                "topic": topic,
                "summary": summary if summary else "Overview of key concepts from material.",
                "key_points": key_points if key_points else ["Key study point from document."],
                "source": filename,
                "page": max(1, page_start),
                "page_end": max(page_start, page_end),
                "is_new_chapter": is_new,
                "tag": tag,
            })
        except Exception as exc:
            logger.warning("[NOTES] Card parse error: %s", exc)

    return valid


async def generate_notes(db: AsyncSession, chat_id: str) -> Note:
    """Generate chapter-aware, continuous study notes strictly budgeted to ~2 pages."""
    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    chat_res = await db.execute(select(Chat).where(Chat.id == cid))
    chat = chat_res.scalar_one_or_none()
    chat_title = chat.title if chat else "Knowledge Space"

    file_buckets = _get_file_chunks(chat_id)
    if not file_buckets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found in this knowledge space. Please upload documents first.",
        )

    all_cards: list[dict[str, Any]] = []

    for filename, chunks in file_buckets.items():
        pages: dict[int, dict[str, Any]] = {}
        for chunk in sorted(chunks, key=lambda item: (int(item["page"]), int(item["chunk_index"]))):
            page_number = int(chunk["page"])
            page = pages.setdefault(page_number, {"page": page_number, "text": ""})
            page["text"] += f"\n{chunk['text']}"

        page_items = list(pages.values())
        current_chapter: str | None = None
        file_cards: list[dict[str, Any]] = []

        total_pages = len(page_items)
        # Target 4 to 5 thematic blocks total across the document so the notes fit cleanly on 2 pages
        target_cards = 4 if total_pages <= 20 else 5
        batch_size = max(1, (total_pages + target_cards - 1) // target_cards)

        for batch_idx, start in enumerate(range(0, len(page_items), batch_size)):
            page_batch = page_items[start:start + batch_size]
            batch_page_nums = [p["page"] for p in page_batch]

            for p in page_batch:
                detected = _detect_chapter_heading(p["text"])
                if detected:
                    current_chapter = detected
                    break

            sanitized_batch = [
                {"page": p["page"], "text": _sanitize_slide_text(p["text"])}
                for p in page_batch
            ]
            prompt = _build_continuous_section_prompt(filename, sanitized_batch, current_chapter)
            logger.info("[NOTES] Synthesizing continuous pages %s from %s (Chapter: %s)", batch_page_nums, filename, current_chapter)
            parsed_batch: list[dict[str, Any]] = []
            try:
                async with ollama_generation_gate:
                    raw = await _call_llm_json(prompt)
                parsed = _parse_and_repair_json(raw)
                normalized = _normalise_cards(
                    parsed,
                    filename,
                    default_chapter=current_chapter or "",
                    fallback_pages=batch_page_nums,
                )
                if normalized:
                    # Enforce 1 comprehensive card per batch to keep overall document at 4-5 cards
                    parsed_batch = normalized[:1]
                    if normalized[-1].get("chapter"):
                        current_chapter = normalized[-1]["chapter"]
            except Exception as exc:
                logger.warning("[NOTES] LLM synthesis error for %s pages %s: %s", filename, batch_page_nums, exc)

            if not parsed_batch:
                fallback_card = _generate_clean_fallback_card(page_batch, filename, batch_idx, current_chapter)
                parsed_batch.append(fallback_card)

            file_cards.extend(parsed_batch)

        all_cards.extend(file_cards)

    # Global fallback if no cards
    if not all_cards:
        for filename, chunks in file_buckets.items():
            clean_name = filename.rsplit(".", 1)[0] if "." in filename else filename
            all_cards.append({
                "id": f"card_fb_{uuid4().hex[:6]}",
                "chapter": "",
                "topic": f"Core Principles: {_clean_topic_title(clean_name)}",
                "summary": "High-yield conceptual summary of document contents for revision.",
                "key_points": ["**Core Principle**: Primary concepts and analytical frameworks."],
                "source": filename,
                "page": 1,
                "page_end": 1,
                "is_new_chapter": True,
                "tag": "Concept",
            })

    note = Note(
        id=uuid4(),
        chat_id=cid,
        title=f"AI Notes: {chat_title}",
        cards=all_cards,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    logger.info("[NOTES] Total consolidated note sections generated: %d across %d files", len(all_cards), len(file_buckets))
    return note


def build_single_file_notes_pdf(
    filename: str,
    cards: list[dict[str, Any]],
    chat_title: str = "Knowledge Space",
) -> bytes:
    """
    Render concise, high-yield revision notes tailored to strictly ~2 pages.
    New topics are prominently bolded with visually distinct headers,
    key points are merged for brevity, and page labels or 'Summary' badges are excluded.
    """
    import fitz

    PAGE_WIDTH = 595.3
    PAGE_HEIGHT = 841.9
    LEFT_MARGIN = 44.0
    RIGHT_MARGIN = 551.0
    USABLE_WIDTH = RIGHT_MARGIN - LEFT_MARGIN
    BOTTOM_LIMIT = 785.0

    document = fitz.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    current_page_num = 1
    cursor_y = 38.0

    def start_new_page() -> bool:
        nonlocal page, current_page_num, cursor_y
        if current_page_num >= 2:
            return False  # Strict 2-page limit!
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        current_page_num += 1
        clean_name = _clean_topic_title(filename.rsplit(".", 1)[0] if "." in filename else filename)
        # Running top header on Page 2
        page.insert_text(
            (LEFT_MARGIN, 34.0),
            f"EXAM REVISION NOTES: {clean_name.upper()} (CONTINUED)",
            fontsize=8.0,
            fontname="hebo",
            color=(0.35, 0.42, 0.52),
        )
        page.draw_line(
            fitz.Point(LEFT_MARGIN, 38.0),
            fitz.Point(RIGHT_MARGIN, 38.0),
            color=(0.82, 0.85, 0.9),
            width=0.6,
        )
        cursor_y = 52.0
        return True

    def add_wrapped_text(
        text: str,
        size: float = 8.6,
        bold: bool = False,
        color=(0.18, 0.2, 0.24),
        indent: float = 0.0,
        prefix_bold: str | None = None,
    ) -> bool:
        nonlocal cursor_y
        font = "hebo" if bold else "helv"
        line_height = size + 3.2

        norm_text = " ".join(text.split())
        if not norm_text and not prefix_bold:
            return True

        full_line = f"{prefix_bold} {norm_text}".strip() if prefix_bold else norm_text
        wrap_chars = max(45, int((USABLE_WIDTH - indent) / (size * 0.52)))
        wrapped_lines = textwrap.wrap(full_line, width=wrap_chars, break_long_words=False) or [""]

        for idx, line in enumerate(wrapped_lines):
            if cursor_y + line_height > BOTTOM_LIMIT:
                if not start_new_page():
                    return False

            x_pos = LEFT_MARGIN + indent
            if idx == 0 and prefix_bold and line.startswith(prefix_bold):
                page.insert_text((x_pos, cursor_y), prefix_bold, fontsize=size, fontname="hebo", color=(0.06, 0.18, 0.42))
                p_width = fitz.get_text_length(prefix_bold + " ", fontname="hebo", fontsize=size)
                remainder = line[len(prefix_bold):].strip()
                if remainder:
                    page.insert_text((x_pos + p_width, cursor_y), remainder, fontsize=size, fontname="helv", color=color)
            else:
                page.insert_text((x_pos, cursor_y), line, fontsize=size, fontname=font, color=color)

            cursor_y += line_height

        return True

    # ── Page 1 Header ──
    clean_doc_name = filename.rsplit(".", 1)[0] if "." in filename else filename
    clean_doc_name = _clean_topic_title(clean_doc_name).upper()

    page.insert_text((LEFT_MARGIN, cursor_y), f"EXAM REVISION NOTES: {clean_doc_name}", fontsize=13.0, fontname="hebo", color=(0.06, 0.18, 0.42))
    cursor_y += 16.0
    sub = f"Source: {filename}   |   Knowledge Space: {chat_title}   |   High-Yield Consolidated Review"
    page.insert_text((LEFT_MARGIN, cursor_y), sub, fontsize=8.0, fontname="helv", color=(0.42, 0.46, 0.52))
    cursor_y += 8.0
    page.draw_line(fitz.Point(LEFT_MARGIN, cursor_y), fitz.Point(RIGHT_MARGIN, cursor_y), color=(0.7, 0.75, 0.82), width=1.0)
    cursor_y += 14.0

    last_chapter: str | None = None
    for idx, card in enumerate(cards, start=1):
        if current_page_num > 2:
            break

        chapter = _clean_topic_title(card.get("chapter") or "")
        is_new_ch = card.get("is_new_chapter") or (chapter and chapter != last_chapter)

        if is_new_ch and chapter and chapter.lower() not in {"general", "summary", "overview", "chapter overview"}:
            last_chapter = chapter
            if cursor_y + 35 > BOTTOM_LIMIT:
                if not start_new_page():
                    break
            cursor_y += 2.0
            page.insert_text((LEFT_MARGIN, cursor_y), f"SECTION: {chapter.upper()}", fontsize=9.0, fontname="hebo", color=(0.25, 0.35, 0.55))
            cursor_y += 12.0

        topic = _clean_topic_title(card.get("topic") or f"Core Concept {idx}")
        topic = re.sub(r'^[•·\-\s]+', '', topic).strip()

        if cursor_y + 60 > BOTTOM_LIMIT:
            if not start_new_page():
                break

        # Prominently Bold New Topic Header with soft banner
        cursor_y += 3.0
        page.draw_rect(
            fitz.Rect(LEFT_MARGIN, cursor_y - 10, RIGHT_MARGIN, cursor_y + 6),
            color=None,
            fill=(0.94, 0.96, 0.99),
        )
        page.draw_line(
            fitz.Point(LEFT_MARGIN, cursor_y - 10),
            fitz.Point(LEFT_MARGIN, cursor_y + 6),
            color=(0.12, 0.35, 0.7),
            width=2.5,
        )
        page.insert_text((LEFT_MARGIN + 8, cursor_y), f"■  {idx}. {topic.upper()}", fontsize=9.6, fontname="hebo", color=(0.06, 0.18, 0.42))
        cursor_y += 14.0

        summary = card.get("summary", "").strip()
        if summary:
            summary_clean = _sanitize_slide_text(summary)
            summary_clean = re.sub(r'(?i)\bpages?\s*\d+([–\-]\d+)?\b', '', summary_clean).strip()
            summary_clean = re.sub(r'(?i)\b(summary|overview)\b:?', '', summary_clean).strip()
            if summary_clean:
                if not add_wrapped_text(summary_clean, size=8.5, color=(0.2, 0.22, 0.26), indent=6):
                    break
                cursor_y += 3.0

        key_points = card.get("key_points", [])
        merged_points = _merge_points_for_brevity(key_points, max_points=3)
        for pt in merged_points:
            pt_clean = _sanitize_slide_text(pt)
            pt_clean = re.sub(r'(?i)\bpages?\s*\d+([–\-]\d+)?\b', '', pt_clean).strip()
            pt_clean = re.sub(r'(?i)\bkey fact:\s*', '', pt_clean).strip()
            if not pt_clean or len(pt_clean) < 5:
                continue

            match = re.match(r'^\*{0,2}([A-Za-z0-9\s\-/]+)\*{0,2}:\s*(.*)$', pt_clean)
            if match and len(match.group(1)) <= 35:
                lead_kw = f"• {match.group(1).strip()}:"
                body = match.group(2).strip()
                if not add_wrapped_text(body, size=8.3, color=(0.15, 0.17, 0.2), indent=12, prefix_bold=lead_kw):
                    break
            else:
                lead_kw = "•"
                if not add_wrapped_text(pt_clean, size=8.3, color=(0.15, 0.17, 0.2), indent=12, prefix_bold=lead_kw):
                    break

        cursor_y += 8.0

    # ── Stamp Footers on all pages (Max 2 pages) ──
    total_pages = len(document)
    for p_idx in range(total_pages):
        p = document[p_idx]
        p.draw_line(fitz.Point(LEFT_MARGIN, 810.0), fitz.Point(RIGHT_MARGIN, 810.0), color=(0.85, 0.88, 0.92), width=0.5)
        p.insert_text((LEFT_MARGIN, 822.0), "RagVault AI Knowledge Hub • High-Yield Revision Summary", fontsize=7.5, fontname="helv", color=(0.5, 0.55, 0.6))
        p.insert_text((RIGHT_MARGIN - 52.0, 822.0), f"Page {p_idx + 1} of {total_pages}", fontsize=7.5, fontname="helv", color=(0.5, 0.55, 0.6))

    return document.tobytes(garbage=4, deflate=True)


def build_notes_zip(note: Note, chat_title: str = "Knowledge Space") -> tuple[bytes, str]:
    """
    Generate separate study note PDFs for every source document,
    and bundle them into a downloadable ZIP archive.
    """
    cards = note.cards or []
    by_source: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        source = card.get("source") or "Document"
        by_source.setdefault(source, []).append(card)

    if not by_source:
        by_source["Document"] = []

    zip_buffer = io.BytesIO()
    seen_names: set[str] = set()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, file_cards in by_source.items():
            pdf_bytes = build_single_file_notes_pdf(filename, file_cards, chat_title)
            clean_name = re.sub(r'[\\/*?:"<>|]', "", filename)
            base_name = clean_name.rsplit(".", 1)[0] if "." in clean_name else clean_name
            base_name = base_name.strip() or "Document"
            pdf_filename = f"Notes - {base_name}.pdf"
            count = 1
            while pdf_filename in seen_names:
                pdf_filename = f"Notes - {base_name}_{count}.pdf"
                count += 1
            seen_names.add(pdf_filename)
            zf.writestr(pdf_filename, pdf_bytes)

    zip_bytes = zip_buffer.getvalue()
    return zip_bytes, f"ragvault-notes-{note.chat_id}.zip"


def build_notes_pdf(note: Note, chat_title: str = "Knowledge Space") -> bytes:
    """Render notes as a searchable text PDF."""
    cards = note.cards or []
    sources = list({c.get("source") for c in cards if c.get("source")})
    doc_name = sources[0] if len(sources) == 1 else (note.title or "Consolidated Study Notes")
    return build_single_file_notes_pdf(doc_name, cards, chat_title)


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
