"""
Quiz router: generation, submission, history, and recommendations.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.chat import Chat
from app.models.quiz import Quiz
from app.models.user import User
from app.schemas.quiz import (
    QuizGenerateRequest,
    QuizResponse,
    QuizResultResponse,
    QuizSubmitRequest,
    RecommendationResponse,
)
from app.services.quiz_service import generate_quiz, submit_quiz
from app.services.recommendation_service import get_recommendations

router = APIRouter(tags=["Quiz"])


async def _verify_chat_ownership(chat_id: str, user: User, db: AsyncSession) -> Chat:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if str(chat.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Access denied.")
    return chat


@router.post("/chats/{chat_id}/quiz", response_model=QuizResponse, status_code=201)
async def create_quiz(
    chat_id: str,
    payload: QuizGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResponse:
    """Generate a quiz from documents in the knowledge space."""
    await _verify_chat_ownership(chat_id, current_user, db)
    quiz = await generate_quiz(
        db=db,
        chat_id=chat_id,
        topic=payload.topic,
        num_questions=payload.num_questions,
    )
    return QuizResponse.model_validate(quiz)


@router.post("/quiz/{quiz_id}/submit", response_model=QuizResultResponse)
async def submit_quiz_answers(
    quiz_id: str,
    payload: QuizSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResultResponse:
    """Submit answers for a quiz and receive a graded result."""
    result = await submit_quiz(db=db, quiz_id=quiz_id, answers=payload.answers)
    return QuizResultResponse(**result)


@router.get("/chats/{chat_id}/quiz-history", response_model=list[QuizResponse])
async def get_quiz_history(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuizResponse]:
    """Return all quizzes taken in a knowledge space, most recent first."""
    await _verify_chat_ownership(chat_id, current_user, db)
    result = await db.execute(
        select(Quiz)
        .where(Quiz.chat_id == chat_id)
        .order_by(desc(Quiz.created_at))
    )
    quizzes = result.scalars().all()
    return [QuizResponse.model_validate(q) for q in quizzes]


@router.get("/chats/{chat_id}/recommendations", response_model=RecommendationResponse)
async def get_study_recommendations(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Generate a personalised study plan based on recent quiz weak topics."""
    await _verify_chat_ownership(chat_id, current_user, db)
    plan = await get_recommendations(db=db, chat_id=chat_id, user_id=str(current_user.id))
    return RecommendationResponse(
        chat_id=chat_id,
        recommendations=plan,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
