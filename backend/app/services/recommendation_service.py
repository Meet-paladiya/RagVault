"""
Recommendation service: LangGraph StateGraph that reads weak topics from quiz
history and generates a personalised Markdown study plan via Ollama LLM.
"""
import logging
from typing import Any, TypedDict
from uuid import UUID

from langchain_community.llms import Ollama
from langgraph.graph import END, StateGraph
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.quiz import Quiz

logger = logging.getLogger(__name__)


# ─── LangGraph State ──────────────────────────────────────────────────────────

class RecommendationState(TypedDict):
    chat_id: str
    chat_title: str
    weak_topics: list[str]       # Aggregated across recent quizzes
    study_plan: str              # Generated markdown study plan


# ─── LangGraph Nodes ─────────────────────────────────────────────────────────

def format_weak_topics_node(state: RecommendationState) -> RecommendationState:
    """Node 1: Deduplicate and format weak topics."""
    raw = state["weak_topics"]
    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in raw:
        clean = t.strip()
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    state["weak_topics"] = deduped
    return state


def generate_study_plan_node(state: RecommendationState) -> RecommendationState:
    """Node 2: Call Ollama to synthesize a personalised study plan."""
    from app.config import get_settings

    cfg = get_settings()
    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)

    topics = state["weak_topics"]
    title = state["chat_title"]

    if not topics:
        state["study_plan"] = (
            f"🎉 **Great job!** You have answered all quiz questions correctly in **{title}**.\n\n"
            "Keep up the good work! Try taking another quiz or uploading more material to challenge yourself."
        )
        return state

    topics_list = "\n".join(f"- {t}" for t in topics[:10])

    prompt = f"""You are an encouraging academic coach and tutor.
A student studying "{title}" recently took a quiz and made mistakes on the following concepts/questions:

{topics_list}

Create a structured, highly actionable study plan in clean Markdown with:
1. 🎯 **Focus Areas**: Group the weak concepts into 2–3 key study themes.
2. 📖 **Review Strategy**: Specific advice on how to master each theme.
3. 💡 **Active Recall Tips**: 2–3 practice questions or memory techniques.
4. ⏰ **Next Steps**: A quick 3-day action plan (Day 1, Day 2, Day 3).

Keep the tone encouraging, structured, and concise. Use bullet points and bold text."""

    try:
        plan = llm.invoke(prompt)
        state["study_plan"] = plan.strip()
    except Exception as exc:
        logger.error("[RECOMMENDATIONS] LLM generation error: %s", exc)
        state["study_plan"] = (
            f"⚠️ **Could not generate study plan**: Ollama model `{cfg.ollama_model}` error.\n"
            f"Please run `ollama pull {cfg.ollama_model}` and try again."
        )

    return state


# ─── Build the Recommendation Graph ──────────────────────────────────────────

def _build_recommendation_graph() -> Any:
    workflow = StateGraph(RecommendationState)
    workflow.add_node("format_weak_topics", format_weak_topics_node)
    workflow.add_node("generate_study_plan", generate_study_plan_node)

    workflow.set_entry_point("format_weak_topics")
    workflow.add_edge("format_weak_topics", "generate_study_plan")
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
    cid = UUID(str(chat_id)) if not isinstance(chat_id, UUID) else chat_id
    # Load chat title for context
    chat = await db.get(Chat, cid)
    chat_title = chat.title if chat else "your course"

    # Load last 5 quiz results
    quiz_result = await db.execute(
        select(Quiz)
        .where(Quiz.chat_id == cid)
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
        chat_id=str(cid),
        chat_title=chat_title,
        weak_topics=all_weak,
        study_plan="",
    )
    final_state = await _recommendation_graph.ainvoke(initial_state)
    return final_state["study_plan"]
