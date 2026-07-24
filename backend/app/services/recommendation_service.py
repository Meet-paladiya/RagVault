"""
Recommendation service: reads recent quiz weak_topics and generates a
personalised study plan via Ollama LLM using a LangGraph node.
"""
import logging
from typing import Any

from langchain_community.llms import Ollama
from langgraph.graph import END, StateGraph
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz
from app.models.chat import Chat

logger = logging.getLogger(__name__)


# ─── LangGraph State ─────────────────────────────────────────────────────────

class RecommendationState(dict):
    chat_id: str
    chat_title: str
    weak_topics: list[str]
    study_plan: str


# ─── LangGraph Nodes ─────────────────────────────────────────────────────────

def gather_weak_topics_node(state: RecommendationState) -> RecommendationState:
    """Aggregate weak topics from state (already loaded from DB)."""
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in state["weak_topics"]:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    state["weak_topics"] = deduped[:20]  # cap at 20 topics
    return state


def generate_study_plan_node(state: RecommendationState) -> RecommendationState:
    """Call Ollama LLM to generate a personalised Markdown study plan."""
    from app.config import get_settings

    cfg = get_settings()

    if not state["weak_topics"]:
        state["study_plan"] = (
            "🎉 Great job! No significant weak areas detected from your recent quizzes. "
            "Keep practising to maintain your understanding."
        )
        return state

    topics_list = "\n".join(f"- {t}" for t in state["weak_topics"])
    prompt = f"""You are an expert academic tutor. A student has been struggling with the following topics
from their recent quiz results in a course called "{state['chat_title']}":

{topics_list}

Create a concise, actionable personalised study plan in Markdown format. Include:
1. A brief prioritised list of topics to review (most important first)
2. For each topic: 1-2 concrete study strategies or resources types (no external URLs)
3. A suggested study schedule (e.g. 30 min per day over one week)
4. One motivational closing sentence

Keep the total response under 400 words. Use clear Markdown headings."""

    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)
    logger.info("[RECOMMEND] Generating study plan for chat %s", state["chat_id"])
    state["study_plan"] = llm.invoke(prompt).strip()
    return state


def _build_recommendation_graph() -> Any:
    workflow: StateGraph = StateGraph(RecommendationState)
    workflow.add_node("gather_weak_topics", gather_weak_topics_node)
    workflow.add_node("generate_study_plan", generate_study_plan_node)
    workflow.set_entry_point("gather_weak_topics")
    workflow.add_edge("gather_weak_topics", "generate_study_plan")
    workflow.add_edge("generate_study_plan", END)
    return workflow.compile()


_recommendation_graph = _build_recommendation_graph()


# ─── Public API ──────────────────────────────────────────────────────────────

async def get_recommendations(
    db: AsyncSession,
    chat_id: str,
    user_id: str,
) -> str:
    """
    Read the last 5 quiz results for a chat, aggregate weak topics,
    and return an LLM-generated Markdown study plan.
    """
    # Load chat title for context
    chat = await db.get(Chat, chat_id)
    chat_title = chat.title if chat else "your course"

    # Load last 5 quiz results
    quiz_result = await db.execute(
        select(Quiz)
        .where(Quiz.chat_id == chat_id)
        .order_by(desc(Quiz.created_at))
        .limit(5)
    )
    quizzes = quiz_result.scalars().all()

    # Collect all weak topics
    all_weak: list[str] = []
    for quiz in quizzes:
        if quiz.weak_topics:
            all_weak.extend(quiz.weak_topics)

    # Run the LangGraph recommendation workflow
    initial_state = RecommendationState(
        chat_id=chat_id,
        chat_title=chat_title,
        weak_topics=all_weak,
        study_plan="",
    )
    final_state = await _recommendation_graph.ainvoke(initial_state)
    return final_state["study_plan"]
