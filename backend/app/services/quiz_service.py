"""
Quiz service: MCQ generation via local LLM in parallel batches, grading, and weak-topic analysis.
"""
import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.models.quiz import Quiz
from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single
from app.services.llm_gate import ollama_generation_gate

logger = logging.getLogger(__name__)


def _representative_chunks(chunks: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Spread general quizzes across the full uploaded collection."""
    if len(chunks) <= limit:
        return chunks
    step = (len(chunks) - 1) / (limit - 1)
    return [chunks[round(index * step)] for index in range(limit)]


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
- Generate MCQs only. Do not generate fill-in-the-blank questions.
- Every question must test a different fact, concept, formula, or application.
- Questions must be unique in meaning, not just different in wording.{exclusion_block}
- 4 concise options per question (1-5 words each), exactly 1 correct answer (indicated by 0-based integer 'answer' index: 0, 1, 2, or 3).
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
    """Send prompt to local OpenAI-compatible / llama.cpp LLM server."""
    cfg = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
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
        chunks = query_collection(chat_id=chat_id, query_embedding=topic_embedding, k=6)

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
