"""
Quiz service: MCQ generation via local Ollama LLM, grading, and weak-topic analysis.
Uses LangGraph for the quiz generation workflow.
"""
import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from langchain_community.llms import Ollama
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz
from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single

logger = logging.getLogger(__name__)


# ─── LangGraph State for Quiz Generation ─────────────────────────────────────

class QuizGenState(dict):
    """Typed state for the quiz generation graph."""
    chat_id: str
    topic: str
    num_questions: int
    chunks: list[dict[str, Any]]
    raw_llm_output: str
    questions: list[dict[str, Any]]


# ─── MCQ Prompt & Parsing ────────────────────────────────────────────────────

_MCQ_SCHEMA = """[
  {
    "id": "q1",
    "question": "Question text here",
    "options": [
      {"id": "a", "text": "Option A"},
      {"id": "b", "text": "Option B"},
      {"id": "c", "text": "Option C"},
      {"id": "d", "text": "Option D"}
    ],
    "correct_option_id": "a",
    "explanation": "Brief explanation of why option A is correct."
  }
]"""


def _build_quiz_prompt(topic: str, context: str, num_questions: int) -> str:
    return f"""You are an expert teacher. Based on the educational material provided below,
generate exactly {num_questions} multiple-choice questions about "{topic}".

Rules:
- Each question must be answerable from the provided material only.
- 4 options per question, exactly one correct answer.
- Include a brief explanation for the correct answer.
- Output ONLY valid JSON — no markdown fences, no extra text.
- Use this exact schema:

{_MCQ_SCHEMA}

=== EDUCATIONAL MATERIAL ===
{context}

=== OUTPUT ({num_questions} questions in JSON) ==="""


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Extract the first JSON array from LLM output (strips markdown fences)."""
    # Remove ```json ... ``` wrappers
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find the first [ ... ] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in LLM output")
    return json.loads(match.group(0))


def _validate_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalise MCQ structure."""
    valid: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        try:
            assert isinstance(q.get("question"), str) and q["question"]
            assert isinstance(q.get("options"), list) and len(q["options"]) >= 2
            assert q.get("correct_option_id") in {o["id"] for o in q["options"]}
            # Ensure id is set
            q.setdefault("id", f"q{i+1}")
            q.setdefault("explanation", "")
            valid.append(q)
        except (AssertionError, KeyError, TypeError) as exc:
            logger.warning("Skipping malformed question %d: %s", i, exc)
    return valid


# ─── Quiz Generation with Retry ──────────────────────────────────────────────

async def generate_quiz(
    db: AsyncSession,
    chat_id: str,
    topic: str,
    num_questions: int = 5,
) -> Quiz:
    """
    Generate a quiz by:
      1. Retrieving relevant chunks from ChromaDB
      2. Calling Ollama LLM to produce structured MCQ JSON (retry up to 3×)
      3. Validating and persisting the quiz in PostgreSQL
    """
    from app.config import get_settings

    cfg = get_settings()

    # ── Retrieve relevant chunks ──────────────────────────────────────────────
    topic_embedding = embed_single(topic)
    chunks = query_collection(chat_id=chat_id, query_embedding=topic_embedding, k=15)

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found in this knowledge space. Please upload documents first.",
        )

    context = "\n\n".join(
        f"[Source: {c['source']}, Page: {c['page']}]\n{c['text']}" for c in chunks
    )

    # ── Call Ollama with retry ────────────────────────────────────────────────
    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)
    prompt = _build_quiz_prompt(topic, context, num_questions)

    questions: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            logger.info("[QUIZ] Attempt %d: calling Ollama for topic '%s'", attempt, topic)
            raw = llm.invoke(prompt)
            parsed = _extract_json_array(raw)
            validated = _validate_questions(parsed)
            if validated:
                questions = validated
                break
        except (json.JSONDecodeError, ValueError, AssertionError) as exc:
            logger.warning("[QUIZ] Attempt %d failed: %s", attempt, exc)
            last_error = exc

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate valid MCQs after 3 attempts. Last error: {last_error}",
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
    logger.info("[QUIZ] Created quiz %s with %d questions", quiz.id, len(questions))
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

    for q in questions:
        qid = q.get("id", "")
        chosen = answers.get(qid)
        if chosen == q.get("correct_option_id"):
            correct_count += 1
        else:
            wrong_topics.append(q.get("question", "")[:80])  # truncate for storage

    total = len(questions)
    score = round(correct_count / total * 100, 1) if total else 0.0

    quiz.score = score
    quiz.weak_topics = wrong_topics
    await db.commit()
    await db.refresh(quiz)

    logger.info(
        "[QUIZ] Graded quiz %s: %d/%d correct (%.1f%%)",
        quiz_id,
        correct_count,
        total,
        score,
    )

    return {
        "quiz_id": quiz_id,
        "score": score,
        "total_questions": total,
        "correct_count": correct_count,
        "weak_topics": wrong_topics,
        "feedback": (
            "Excellent work!" if score >= 80
            else "Good effort! Review the weak topics below."
            if score >= 50
            else "Keep studying — focus on the topics marked below."
        ),
    }
