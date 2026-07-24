"""
RAG service implemented as an explicit LangGraph StateGraph.

Graph topology:
  embed_question → retrieve_chunks → assemble_context → generate_answer → extract_citations → END

Supports both streaming (SSE token-by-token) and non-streaming response modes.
LLM calls go to Ollama running locally via langchain_community.
"""
import json
import logging
from typing import Any, AsyncGenerator, TypedDict

from langchain_community.llms import Ollama
from langgraph.graph import END, StateGraph

from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single

logger = logging.getLogger(__name__)


# ─── LangGraph State ──────────────────────────────────────────────────────────

class RAGState(TypedDict):
    question: str
    chat_id: str
    chat_history: list[dict[str, str]]   # [{role, content}, ...]
    top_k: int

    # Populated by nodes
    query_embedding: list[float]
    retrieved_chunks: list[dict[str, Any]]
    context: str
    answer: str
    citations: list[dict[str, Any]]      # [{source, page}, ...]


# ─── LangGraph Nodes ─────────────────────────────────────────────────────────

def embed_question_node(state: RAGState) -> RAGState:
    """Node 1: Embed the user question using the same model used at ingest time."""
    logger.debug("[RAG] Embedding question")
    state["query_embedding"] = embed_single(state["question"])
    return state


def retrieve_chunks_node(state: RAGState) -> RAGState:
    """Node 2: Retrieve top-k similar chunks from the chat's ChromaDB collection."""
    logger.debug("[RAG] Retrieving chunks (top_k=%d)", state["top_k"])
    chunks = query_collection(
        chat_id=state["chat_id"],
        query_embedding=state["query_embedding"],
        k=state["top_k"],
    )
    state["retrieved_chunks"] = chunks
    logger.info("[RAG] Retrieved %d chunks", len(chunks))
    return state


def assemble_context_node(state: RAGState) -> RAGState:
    """Node 3: Format retrieved chunks into a numbered context block."""
    parts: list[str] = []
    for i, chunk in enumerate(state["retrieved_chunks"], start=1):
        parts.append(
            f"[{i}] Source: {chunk['source']} | Page: {chunk['page']}\n{chunk['text']}"
        )
    state["context"] = "\n\n---\n\n".join(parts) if parts else "No relevant context found."
    return state


def _build_prompt(state: RAGState) -> str:
    """Construct the full prompt for the LLM."""
    history_lines: list[str] = []
    for msg in state["chat_history"][-6:]:  # last 3 turns
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior conversation)"

    return f"""You are a knowledgeable AI tutor. Your task is to answer the student's question
based ONLY on the provided context. Do not use information outside of the context.
If the answer cannot be found in the context, say so clearly.

When referencing information, cite the source using this format: [Source: <filename>, Page: <N>]

=== CONTEXT ===
{state['context']}

=== CONVERSATION HISTORY ===
{history_block}

=== STUDENT QUESTION ===
{state['question']}

=== YOUR ANSWER ==="""


def generate_answer_node(state: RAGState) -> RAGState:
    """Node 4: Call Ollama LLM with the assembled prompt (non-streaming path)."""
    from app.config import get_settings

    cfg = get_settings()
    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)

    prompt = _build_prompt(state)
    try:
        answer = llm.invoke(prompt)
        state["answer"] = answer.strip()
    except Exception as exc:
        logger.error("[RAG] LLM generation error: %s", exc)
        state["answer"] = (
            f"⚠️ **LLM Error**: Could not generate response using Ollama model `{cfg.ollama_model}`.\n"
            f"Please run `ollama pull {cfg.ollama_model}` in your terminal."
        )
    return state


def extract_citations_node(state: RAGState) -> RAGState:
    """
    Node 5: Build a deduplicated citation list from the retrieved chunk metadata.
    Citations are derived from metadata, NOT from LLM hallucination.
    """
    seen: set[tuple[str, int]] = set()
    citations: list[dict[str, Any]] = []
    for chunk in state["retrieved_chunks"]:
        key = (chunk["source"], chunk["page"])
        if key not in seen:
            seen.add(key)
            citations.append({"source": chunk["source"], "page": chunk["page"]})
    state["citations"] = citations
    return state


# ─── Build & Compile the LangGraph ───────────────────────────────────────────

def _build_rag_graph() -> Any:
    workflow: StateGraph = StateGraph(RAGState)

    workflow.add_node("embed_question", embed_question_node)
    workflow.add_node("retrieve_chunks", retrieve_chunks_node)
    workflow.add_node("assemble_context", assemble_context_node)
    workflow.add_node("generate_answer", generate_answer_node)
    workflow.add_node("extract_citations", extract_citations_node)

    workflow.set_entry_point("embed_question")
    workflow.add_edge("embed_question", "retrieve_chunks")
    workflow.add_edge("retrieve_chunks", "assemble_context")
    workflow.add_edge("assemble_context", "generate_answer")
    workflow.add_edge("generate_answer", "extract_citations")
    workflow.add_edge("extract_citations", END)

    return workflow.compile()


rag_graph = _build_rag_graph()


# ─── Public API ──────────────────────────────────────────────────────────────

async def run_rag(
    question: str,
    chat_id: str,
    chat_history: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Execute the full RAG LangGraph and return the complete result.

    Returns:
        {"answer": str, "citations": List[{source, page}]}
    """
    from app.config import get_settings

    cfg = get_settings()

    initial_state: RAGState = {
        "question": question,
        "chat_id": chat_id,
        "chat_history": chat_history,
        "top_k": cfg.top_k,
        "query_embedding": [],
        "retrieved_chunks": [],
        "context": "",
        "answer": "",
        "citations": [],
    }

    # Run the graph (synchronous nodes wrapped in async invoke)
    final_state: RAGState = await rag_graph.ainvoke(initial_state)
    return {
        "answer": final_state["answer"],
        "citations": final_state["citations"],
    }


async def stream_rag(
    question: str,
    chat_id: str,
    chat_history: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """
    Stream the RAG answer token-by-token as SSE events.

    Yields lines in the format:
        data: <token>\\n\\n
    Terminates with:
        data: [DONE]\\n\\n

    The citations JSON is sent as a final metadata event before [DONE]:
        data: __citations__:<json>\\n\\n
    """
    from app.config import get_settings

    cfg = get_settings()

    # ── Steps 1-3: embed → retrieve → assemble context (run synchronously) ───
    query_embedding = embed_single(question)
    retrieved_chunks = query_collection(
        chat_id=chat_id,
        query_embedding=query_embedding,
        k=cfg.top_k,
    )

    # Build context block
    parts: list[str] = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        parts.append(
            f"[{i}] Source: {chunk['source']} | Page: {chunk['page']}\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(parts) if parts else "No relevant context found."

    # Build prompt
    history_lines: list[str] = []
    for msg in chat_history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior conversation)"

    prompt = f"""You are a knowledgeable AI tutor. Answer the student's question based ONLY on the provided context.
If the answer cannot be found in the context, say so clearly.
Cite sources as [Source: <filename>, Page: <N>].

=== CONTEXT ===
{context}

=== CONVERSATION HISTORY ===
{history_block}

=== STUDENT QUESTION ===
{question}

=== YOUR ANSWER ==="""

    # ── Step 4: Stream tokens from Ollama ────────────────────────────────────
    llm = Ollama(base_url=cfg.ollama_base_url, model=cfg.ollama_model)
    logger.info("[RAG:stream] Streaming from Ollama model: %s", cfg.ollama_model)

    try:
        async for chunk in llm.astream(prompt):
            if chunk:
                yield f"data: {chunk}\n\n"
    except Exception as exc:
        logger.error("[RAG:stream] LLM streaming error: %s", exc)
        err_msg = (
            f"\n\n⚠️ **LLM Model Not Found**: Ollama model `{cfg.ollama_model}` is not pulled yet.\n"
            f"Please run `ollama pull {cfg.ollama_model}` in your terminal."
        )
        yield f"data: {err_msg}\n\n"

    # ── Step 5: Emit deduplicated citations as metadata event ─────────────────
    seen: set[tuple[str, int]] = set()
    citations: list[dict[str, Any]] = []
    for chunk in retrieved_chunks:
        key = (chunk["source"], chunk["page"])
        if key not in seen:
            seen.add(key)
            citations.append({"source": chunk["source"], "page": chunk["page"]})

    yield f"data: __citations__:{json.dumps(citations)}\n\n"
    yield "data: [DONE]\n\n"
