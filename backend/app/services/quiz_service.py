"""
Quiz service: MCQ generation via local LLM in parallel batches, grading, and weak-topic analysis.
"""
import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Callable, Coroutine
from uuid import UUID, uuid4
from datetime import datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.quiz import Quiz
from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single
from app.services.llm_gate import ollama_generation_gate

logger = logging.getLogger(__name__)


_ADMIN_SYLLABUS_PATTERNS = [
    r"\bco\s*[-–—:]?\s*[0-9]\b",
    r"\bpo\s*[-–—:]?\s*[0-9]\b",
    r"\bcourse\s+outcomes?\b",
    r"\bcourse\s+objectives?\b",
    r"\bprogram\s+outcomes?\b",
    r"\bcourse\s+code\b",
    r"\bevaluation\s+scheme\b",
    r"\bmarking\s+scheme\b",
    r"\bteaching\s+scheme\b",
    r"\bcredits?\s*:\s*[0-9]\b",
    r"\bprerequisites?\s*:",
    r"\btext\s*books?\s*:",
    r"\breference\s*books?\s*:",
    r"\blecture\s+hours?\b",
]

_SYLLABUS_META_QUESTION_REGEX = re.compile(
    r"\b(co\s*[-–—:]?\s*[0-9]|po\s*[-–—:]?\s*[0-9]|course\s+outcome|course\s+objective|"
    r"program\s+outcome|which\s+(unit|module|chapter|syllabus|course)|"
    r"course\s+code|credit\s+hour|marking\s+scheme|evaluation\s+scheme|"
    r"prescribed\s+textbook|reference\s+book)\b",
    re.IGNORECASE,
)


def _is_syllabus_admin_chunk(text: str) -> bool:
    """Detect if a chunk is purely administrative/syllabus metadata rather than actual educational content."""
    lower = text.lower()
    matches = sum(1 for p in _ADMIN_SYLLABUS_PATTERNS if re.search(p, lower))
    if matches >= 2 or re.search(r"\bcourse\s+outcomes?\b.*\bco\s*[-–—:]?\s*[0-9]\b", lower, re.DOTALL):
        return True
    return False


def _filter_educational_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize substantive content chunks over administrative syllabus front-matter."""
    content_chunks = [c for c in chunks if not _is_syllabus_admin_chunk(c.get("text", ""))]
    if content_chunks:
        return content_chunks
    return chunks


def _representative_chunks(chunks: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Spread general quizzes across the full uploaded collection, avoiding syllabus front-matter."""
    substantive = _filter_educational_chunks(chunks)
    if len(substantive) <= limit:
        return substantive
    step = (len(substantive) - 1) / (limit - 1)
    return [substantive[round(index * step)] for index in range(limit)]


# ─── Ultra-Compact Schema for High-Speed Generation ─────────────────────────

_COMPACT_SCHEMA = """[
  {
        "question": "A clear multiple-choice question",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "answer": 0,
    "explanation": "Clear 2-3 sentence paragraph explanation detailing why the correct answer is right and clarifying the key concept."
  }
]"""


def _build_batch_prompt(
    topic: str,
    context: str,
    count: int = 10,
    excluded_questions: list[str] | None = None,
    focus_angle: str = "core",
) -> str:
    if topic == "General Summary":
        if focus_angle == "core":
            focus = "Focus on foundational concepts, key terminology, definitions, and core principles."
        elif focus_angle == "applied":
            focus = "Focus on practical applications, relationships, edge cases, formulas, and problem-solving scenarios."
        else:
            focus = "Cover important concepts across all of the provided document content."
    else:
        if focus_angle == "core":
            focus = (
                f'Every question must directly test core definitions and fundamental concepts of "{topic}".'
            )
        elif focus_angle == "applied":
            focus = (
                f'Every question must test practical scenarios, calculations, or relationships related to "{topic}".'
            )
        else:
            focus = f'Every question must directly test the specific topic "{topic}".'

    excluded = excluded_questions or []
    exclusion_block = ""
    if excluded:
        exclusion_block = (
            "\nDo not repeat or paraphrase any of these questions from the same quiz:\n"
            + "\n".join(f"- {question}" for question in excluded)
        )

    return f"""Based on the educational text below, generate exactly {count} standard multiple-choice questions (MCQs) about "{topic}".

Rules:
- {focus}
- CRITICAL: Every question must test ACTUAL academic/subject-matter concepts, definitions, formulas, theories, algorithms, mechanisms, or practical applications.
- STRICTLY FORBIDDEN: NEVER generate questions about syllabus structure, course administration, or course outcome codes. Do NOT ask "What is CO-1/CO-2/PO-1?", "What does Course Outcome X focus on?", "Which unit/module covers X?", or questions about course codes, credits, prerequisites, grading schemes, evaluation criteria, or textbook/author names.
- If the text is a syllabus or outline listing topics (e.g. "CO-1: Convolutional Neural Networks, Pooling"), ask conceptual questions testing knowledge of the concept itself (e.g. "What is the primary function of max pooling in CNNs?"), NEVER ask about the syllabus description or outcome label.
- Generate MCQs only. Do not generate fill-in-the-blank questions.
- Every question must test a different fact, concept, formula, or application.
- Questions must be unique in meaning, not just different in wording.{exclusion_block}
- 4 concise options per question (1-5 words each), exactly 1 correct answer (indicated by 0-based integer 'answer' index: 0, 1, 2, or 3).
- Options must NEVER be outcome codes or unit names (e.g. no options like "CO-1", "CO-2", "Unit 1", "Unit 2").
- Provide a 1-sentence concise explanation (max 15 words) explaining why the correct answer is true.
- Output ONLY valid JSON array — no markdown fences, no extra text.
- Use this exact schema:
{_COMPACT_SCHEMA}

TEXT:
{context[:2500]}

JSON ARRAY:"""


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Extract JSON array or object wrapper from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip()

    def _extract_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ["questions", "mcqs", "items", "quiz", "data"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            if "question" in data and "options" in data:
                return [data]
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
        return []

    # Try 1: Direct parse
    try:
        res = json.loads(text)
        extracted = _extract_list(res)
        if extracted:
            return extracted
    except Exception:
        pass

    # Try 2: Regex capture array or dict
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

    raise ValueError("No valid JSON questions found in LLM output")


def _normalise_compact_questions(questions: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    valid = []
    option_ids = ["a", "b", "c", "d"]
    for i, q in enumerate(questions):
        try:
            q_text = str(q.get("question", "")).strip()
            options_raw = q.get("options", [])
            if not q_text or not isinstance(options_raw, list) or len(options_raw) < 4:
                continue

            # Drop syllabus administrative/meta-questions (e.g. "What is the primary focus of CO-1?")
            if _SYLLABUS_META_QUESTION_REGEX.search(q_text):
                logger.info("[QUIZ] Dropped syllabus meta-question: %r", q_text)
                continue

            # Drop questions where options are syllabus outcomes/units
            if any(_SYLLABUS_META_QUESTION_REGEX.search(str(opt)) for opt in options_raw):
                logger.info("[QUIZ] Dropped question with syllabus meta-options: %r", q_text)
                continue

            ans_raw = q.get("answer", 0)
            ans_idx = 0
            if isinstance(ans_raw, int):
                ans_idx = ans_raw
            elif isinstance(ans_raw, str):
                clean_ans = ans_raw.strip().lower()
                if clean_ans.isdigit():
                    ans_idx = int(clean_ans)
                elif clean_ans in ["a", "b", "c", "d"]:
                    ans_idx = ["a", "b", "c", "d"].index(clean_ans)
                elif clean_ans in ["0", "1", "2", "3"]:
                    ans_idx = int(clean_ans)
                else:
                    for opt_i, opt_val in enumerate(options_raw[:4]):
                        if str(opt_val).strip().lower() == clean_ans:
                            ans_idx = opt_i
                            break

            if not isinstance(ans_idx, int) or ans_idx < 0 or ans_idx >= len(options_raw[:4]):
                ans_idx = 0

            formatted_options = []
            for j, opt in enumerate(options_raw[:4]):
                oid = option_ids[j] if j < 4 else f"opt_{j}"
                formatted_options.append({"id": oid, "text": str(opt).strip()})

            correct_id = formatted_options[ans_idx]["id"] if ans_idx < len(formatted_options) else "a"

            valid.append({
                "id": f"{prefix}_{i+1}",
                "question": q_text,
                "options": formatted_options,
                "correct_option_id": correct_id,
                "explanation": str(q.get("explanation", "")).strip(),
            })
        except Exception as exc:
            logger.warning("[QUIZ] Question normalization error: %s", exc)
    return valid


async def _invoke_llm_async(prompt: str) -> str:
    """Send prompt to local OpenAI-compatible / llama.cpp LLM server.

    Acquires the global generation semaphore so quiz generation never
    races with an active chat stream on a single-threaded CPU LLM.
    """
    cfg = get_settings()
    async with ollama_generation_gate:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{cfg.llm_base_url}/chat/completions",
                json={
                    "model": cfg.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


async def _fetch_question_batch(prompt: str, prefix: str) -> list[dict[str, Any]]:
    """Fetch a single question batch with 2 retries."""
    for attempt in range(1, 3):
        try:
            logger.info("[QUIZ] Generating batch '%s' (attempt %d)...", prefix, attempt)
            raw = await _invoke_llm_async(prompt)
            parsed = _extract_json_array(raw)
            validated = _normalise_compact_questions(parsed, prefix)
            if validated:
                logger.info("[QUIZ] Batch '%s' produced %d valid questions.", prefix, len(validated))
                return validated
        except Exception as exc:
            logger.warning("[QUIZ] Batch '%s' attempt %d failed: %s", prefix, attempt, exc)
    return []


def _calculate_batch_sizes(total: int, initial_batch_size: int = 3) -> list[int]:
    """Calculate balanced batch sizes starting with a fast initial batch (e.g., 3 questions)."""
    if total <= initial_batch_size:
        return [max(1, total)]
    sizes = [initial_batch_size]
    remaining = total - initial_batch_size
    while remaining > 0:
        if remaining <= 6:
            sizes.append(remaining)
            break
        elif remaining == 7:
            sizes.extend([3, 4])
            break
        elif remaining == 8:
            sizes.extend([4, 4])
            break
        elif remaining <= 12:
            half = remaining // 2
            sizes.append(half)
            sizes.append(remaining - half)
            break
        else:
            take = 6 if remaining % 5 != 0 else 5
            sizes.append(take)
            remaining -= take
    return sizes


def _get_batch_context(chunks: list[dict[str, Any]], batch_idx: int, total_batches: int) -> str:
    """Slice retrieved chunks across batches so each batch tests diverse document areas."""
    if len(chunks) <= 3 or total_batches <= 1:
        selected = chunks
    else:
        chunk_count = len(chunks)
        window_size = max(2, (chunk_count // total_batches) + 2)
        start_idx = (batch_idx * (chunk_count - window_size)) // max(1, total_batches - 1) if total_batches > 1 else 0
        start_idx = max(0, min(start_idx, chunk_count - window_size))
        selected = chunks[start_idx : start_idx + window_size]
        if not selected:
            selected = chunks
    return "\n\n".join(
        f"[Source: {c['source']}, Page: {c['page']}]\n{c['text']}" for c in selected
    )


async def generate_quiz_stream(
    chat_id: str,
    topic: str,
    num_questions: int = 20,
    initial_batch_size: int = 3,
    check_disconnected: Callable[[], Coroutine[Any, Any, bool]] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Progressively generate a quiz in batches and yield Server-Sent Events (SSE).

    1. Immediately emits 'init' with quiz metadata.
    2. Generates initial small batch (e.g. 2-3 MCQs) in ~3s and emits 'batch'.
    3. Concurrently commits questions to PostgreSQL so the quiz is always in a persistent state.
    4. Generates remaining batches in background, updating DB and emitting 'batch' events.
    5. Emits 'done' when all questions are generated or loop finishes.
    """
    quiz_id = uuid4()
    cid = UUID(chat_id)

    # 1. Retrieve relevant chunks
    if topic == "General Summary":
        from app.utils.chroma_client import get_all_chunks
        chunks = _representative_chunks(get_all_chunks(chat_id=chat_id, limit=2000), limit=12)
    else:
        topic_embedding = embed_single(topic)
        raw_chunks = query_collection(chat_id=chat_id, query_embedding=topic_embedding, k=16)
        chunks = _filter_educational_chunks(raw_chunks)[:8]

    if not chunks:
        err_msg = "No documents found in this knowledge space. Please upload documents first."
        yield f"data: {json.dumps({'type': 'error', 'detail': err_msg})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 2. Emit initial metadata event
    yield f"data: {json.dumps({'type': 'init', 'quiz_id': str(quiz_id), 'chat_id': chat_id, 'topic': topic, 'target_total': num_questions, 'created_at': datetime.utcnow().isoformat()})}\n\n"

    batch_sizes = _calculate_batch_sizes(num_questions, initial_batch_size=initial_batch_size)
    total_batches = len(batch_sizes)
    all_questions: list[dict[str, Any]] = []
    angles = ["core", "applied", "detailed", "synthesis"]

    for batch_idx, batch_count in enumerate(batch_sizes):
        # Graceful cancellation if client disconnected
        if check_disconnected:
            try:
                if await check_disconnected():
                    logger.info("[QUIZ STREAM] Client disconnected. Aborting generation at batch %d.", batch_idx + 1)
                    break
            except Exception:
                pass

        focus_angle = angles[batch_idx % len(angles)]
        context = _get_batch_context(chunks, batch_idx, total_batches)

        # Exclude recent questions from earlier batches to prevent repetition
        excluded = [q.get("question", "") for q in all_questions[-10:] if q.get("question")]
        prompt = _build_batch_prompt(
            topic=topic,
            context=context,
            count=batch_count,
            excluded_questions=excluded,
            focus_angle=focus_angle,
        )

        batch_prefix = f"b{batch_idx + 1}"
        new_questions = await _fetch_question_batch(prompt, batch_prefix)

        # Fallback retry if needed for the initial fast batch
        if not new_questions and batch_idx == 0:
            fallback_prompt = _build_batch_prompt(topic=topic, context=context, count=batch_count, focus_angle="core")
            new_questions = await _fetch_question_batch(fallback_prompt, "b1_fb")

        if new_questions:
            # Assign sequential continuous IDs: q_1, q_2, ...
            for i, q in enumerate(new_questions):
                q["id"] = f"q_{len(all_questions) + i + 1}"
            all_questions.extend(new_questions)

            # Persist incrementally to database using fresh session
            try:
                async with AsyncSessionLocal() as session:
                    if batch_idx == 0 or len(all_questions) == len(new_questions):
                        quiz = Quiz(
                            id=quiz_id,
                            chat_id=cid,
                            topic=topic,
                            total_questions=len(all_questions),
                            questions=all_questions,
                            score=None,
                            weak_topics=None,
                            created_at=datetime.utcnow(),
                        )
                        session.add(quiz)
                    else:
                        db_res = await session.execute(select(Quiz).where(Quiz.id == quiz_id))
                        quiz = db_res.scalar_one_or_none()
                        if quiz:
                            quiz.questions = list(all_questions)
                            quiz.total_questions = len(all_questions)
                            flag_modified(quiz, "questions")
                    await session.commit()
            except Exception as db_exc:
                logger.error("[QUIZ STREAM] Failed saving batch %d to DB: %s", batch_idx + 1, db_exc)

            # Emit batch event
            is_last_batch = (batch_idx == total_batches - 1) or (len(all_questions) >= num_questions)
            batch_payload = {
                "type": "batch",
                "quiz_id": str(quiz_id),
                "batch_index": batch_idx + 1,
                "new_questions": new_questions,
                "total_loaded": len(all_questions),
                "target_total": num_questions,
                "is_complete": is_last_batch,
            }
            yield f"data: {json.dumps(batch_payload)}\n\n"

            if len(all_questions) >= num_questions:
                break
        else:
            logger.warning("[QUIZ STREAM] Batch %d produced 0 questions.", batch_idx + 1)

    if not all_questions:
        err_msg = "Failed to generate valid quiz questions from local LLM. Please try again."
        yield f"data: {json.dumps({'type': 'error', 'detail': err_msg})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 3. Emit done event
    done_payload = {
        "type": "done",
        "quiz_id": str(quiz_id),
        "total_questions": len(all_questions),
        "is_complete": True,
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
    yield "data: [DONE]\n\n"


# ─── Parallel Quiz Generation ────────────────────────────────────────────────

async def generate_quiz(
    db: AsyncSession,
    chat_id: str,
    topic: str,
    num_questions: int = 20,
) -> Quiz:
    """
    Generate a quiz containing unique MCQs only. The frontend requests 20 questions.
    """
    # ── Retrieve relevant chunks ──────────────────────────────────────────────
    if topic == "General Summary":
        from app.utils.chroma_client import get_all_chunks
        chunks = _representative_chunks(get_all_chunks(chat_id=chat_id, limit=2000), limit=10)
    else:
        topic_embedding = embed_single(topic)
        raw_chunks = query_collection(chat_id=chat_id, query_embedding=topic_embedding, k=14)
        chunks = _filter_educational_chunks(raw_chunks)[:6]

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found in this knowledge space. Please upload documents first.",
        )

    context = "\n\n".join(
        f"[Source: {c['source']}, Page: {c['page']}]\n{c['text']}" for c in chunks
    )

    # ── Dispatch parallel batch requests to LLM ──────────────────────────────
    prompt_mcq = _build_batch_prompt(topic, context, count=10, focus_angle="core")
    prompt_blank = _build_batch_prompt(topic, context, count=10, focus_angle="applied")

    mcq_task = _fetch_question_batch(prompt_mcq, "mcq")
    blank_task = _fetch_question_batch(prompt_blank, "blank")

    logger.info("[QUIZ] Dispatching parallel question batches (core + applied) to local LLM...")
    mcqs, blanks = await asyncio.gather(mcq_task, blank_task)

    questions = mcqs + blanks

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate valid quiz questions from local LLM. Please try again.",
        )

    for index, question in enumerate(questions, start=1):
        question["id"] = f"q_{index}"

    # ── Persist quiz ──────────────────────────────────────────────────────────
    quiz = Quiz(
        id=uuid4(),
        chat_id=UUID(chat_id),
        topic=topic,
        total_questions=len(questions),
        questions=questions,
        score=None,
        weak_topics=None,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    logger.info("[QUIZ] Created quiz %s with %d unique MCQs", quiz.id, len(questions))
    return quiz


async def submit_quiz(
    db: AsyncSession,
    quiz_id: str,
    answers: dict[str, str],
) -> dict[str, Any]:
    """
    Grade a quiz submission.
    answers: {question_id -> chosen_option_id}

    Returns grading result and updates the quiz record with score + weak_topics.
    """
    result = await db.execute(select(Quiz).where(Quiz.id == UUID(quiz_id)))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    questions: list[dict[str, Any]] = quiz.questions or []
    correct_count = 0
    wrong_topics: list[str] = []
    wrong_questions: list[dict[str, Any]] = []

    updated_questions: list[dict[str, Any]] = []
    for q in questions:
        qid = q.get("id", "")
        chosen = answers.get(qid)
        correct_id = q.get("correct_option_id") or q.get("answer")
        opts = q.get("options", [])

        user_opt_text = next((str(opt.get("text", "")).strip() for opt in opts if isinstance(opt, dict) and opt.get("id") == chosen), "Not Answered")
        correct_opt_text = next((str(opt.get("text", "")).strip() for opt in opts if isinstance(opt, dict) and opt.get("id") == correct_id), "Unknown")
        q_text = str(q.get("question", "")).strip()
        explanation = str(q.get("explanation", "")).strip()

        if chosen == correct_id:
            correct_count += 1
        else:
            if not explanation:
                explanation = f"The correct answer is '{correct_opt_text}'. Please review the study materials for more details on this concept."

            wrong_topics.append(q_text[:80])
            wrong_questions.append({
                "question_id": qid,
                "question": q_text,
                "user_answer": user_opt_text,
                "correct_answer": correct_opt_text,
                "explanation": explanation,
            })

        q_copy = dict(q)
        q_copy["user_answer"] = chosen
        q_copy["user_answer_text"] = user_opt_text
        q_copy["correct_answer_text"] = correct_opt_text
        updated_questions.append(q_copy)

    total = len(questions)
    score = round(correct_count / total * 100, 1) if total else 0.0

    quiz.score = score
    quiz.weak_topics = wrong_topics
    quiz.questions = updated_questions
    flag_modified(quiz, "questions")
    await db.commit()
    await db.refresh(quiz)

    logger.info(
        "[QUIZ] Graded quiz %s: %d/%d correct (%.1f%%, %d wrong)",
        quiz_id,
        correct_count,
        total,
        score,
        len(wrong_questions),
    )

    return {
        "quiz_id": quiz_id,
        "score": score,
        "total_questions": total,
        "correct_count": correct_count,
        "weak_topics": wrong_topics,
        "wrong_questions": wrong_questions,
        "feedback": (
            "Excellent work!" if score >= 80
            else "Good effort! Review the incorrect questions below."
            if score >= 50
            else "Keep studying — review the paragraph explanations below for your incorrect answers."
        ),
    }
    