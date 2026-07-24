from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import List, Dict, Optional

class MCQOption(BaseModel):
    id: str
    text: str

class MCQQuestion(BaseModel):
    id: str
    question: str
    options: List[MCQOption]
    correct_option_id: str
    explanation: str

class QuizGenerateRequest(BaseModel):
    topic: str
    num_questions: int = 5

class QuizResponse(BaseModel):
    id: UUID
    chat_id: UUID
    topic: str
    questions: List[MCQQuestion]
    created_at: datetime

    class Config:
        from_attributes = True

class QuizSubmitRequest(BaseModel):
    answers: Dict[str, str]

class QuizResultResponse(BaseModel):
    quiz_id: UUID
    score: float
    total_questions: int
    correct_count: int
    weak_topics: List[str]
    feedback: str

class RecommendationResponse(BaseModel):
    chat_id: UUID
    recommendations: str
    generated_at: datetime
