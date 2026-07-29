"""
Quiz service: MCQ generation via local Ollama LLM in parallel batches, grading, and weak-topic analysis.
"""
import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from langchain_community.llms import Ollama
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz
from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single

logger = logging.getLogger(__name__)


# ─── Ultra-Compact Schema for High-Speed Generation ─────────────────────────

_COMPACT_SCHEMA = """[
  {
    "question": "Question text here (or sentence with '______' for fill in the blanks)",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "answer": 0,
    "explanation": "Clear 2-3 sentence paragraph explanation detailing why the correct answer is right and clarifying the key concept."
  }
]"""


def _build_batch_prompt(topic: str, context: str, qtype: str, count: int = 10) -> str:
    if qtype == "mcq":
        instructions = f"Exactly {count} standard Multiple-Choice Questions (MCQs)."
    else:
        instructions = f"Exactly {count} Fill in the Blank questions, where question text has a '______' placeholder."

    return f"""Based on the educational text below, generate {instructions} about "{topic}".

Rules:
- 4 concise options per question, exactly 1 correct answer (indicated by 0-based integer 'answer' index: 0, 1, 2, or 3).
- Provide a clear, educational 2 to 3 sentence paragraph explanation explaining the concept and why the correct answer is true.
- Output ONLY valid JSON — no markdown fences, no extra text.
- Use this exact schema:
{_COMPACT_SCHEMA}

TEXT:
{context[:2500]}

JSON ARRAY:"""


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Extract the first JSON array from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in LLM output")
    return json.loads(match.group(0))


def _normalise_compact_questions(questions: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    valid = []
    option_ids = ["a", "b", "c", "d"]
    for i, q in enumerate(questions):
        try:
            q_text = str(q.get("question", "")).strip()
            options_raw = q.get("options", [])
            if not q_text or not isinstance(options_raw, list) or len(options_raw) < 2:
                continue

            ans_idx = q.get("answer", 0)
            if not isinstance(ans_idx, int) or ans_idx < 0 or ans_idx >= len(options_raw):
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


def _invoke_llm(llm: Ollama, prompt: str) -> str:
    return llm.invoke(prompt)


async def _fetch_question_batch(llm: Ollama, prompt: str, prefix: str) -> list[dict[str, Any]]:
    """Fetch a single question batch with 2 retries."""
    for attempt in range(1, 3):
        try:
            logger.info("[QUIZ] Generating batch '%s' (attempt %d)...", prefix, attempt)
            raw = await asyncio.to_thread(_invoke_llm, llm, prompt)
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
    Generate a 20-question quiz (10 MCQs + 10 Fill-in-the-blanks) in parallel batches.
    """
    from app.config import get_settings

    cfg = get_settings()

    # ── Retrieve relevant chunks ──────────────────────────────────────────────
    if topic == "General Summary":
        from app.utils.chroma_client import get_all_chunks
        chunks = get_all_chunks(chat_id=chat_id, limit=10)
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

    # ── Dispatch parallel batch requests to Ollama ───────────────────────────
    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model, temperature=0.2)

    prompt_mcq = _build_batch_prompt(topic, context, "mcq", count=10)
    prompt_blank = _build_batch_prompt(topic, context, "blank", count=10)

    mcq_task = _fetch_question_batch(llm, prompt_mcq, "mcq")
    blank_task = _fetch_question_batch(llm, prompt_blank, "blank")

    logger.info("[QUIZ] Dispatching parallel MCQ & Fill-in-blank batches to Ollama...")
    mcqs, blanks = await asyncio.gather(mcq_task, blank_task)

    questions = mcqs + blanks

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate valid quiz questions from Ollama. Please try again.",
        )

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
    logger.info("[QUIZ] Created quiz %s with %d total questions (%d MCQs + %d Blanks)", quiz.id, len(questions), len(mcqs), len(blanks))
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

    for q in questions:
        qid = q.get("id", "")
        chosen = answers.get(qid)
        correct_id = q.get("correct_option_id")
        opts = q.get("options", [])

        if chosen == correct_id:
            correct_count += 1
        else:
            user_opt_text = next((str(opt.get("text", "")).strip() for opt in opts if opt.get("id") == chosen), "Not Answered")
            correct_opt_text = next((str(opt.get("text", "")).strip() for opt in opts if opt.get("id") == correct_id), "Unknown")
            q_text = str(q.get("question", "")).strip()
            explanation = str(q.get("explanation", "")).strip()
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

    total = len(questions)
    score = round(correct_count / total * 100, 1) if total else 0.0

    quiz.score = score
    quiz.weak_topics = wrong_topics
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
