"""
RAG service implemented as an explicit LangGraph StateGraph.

Graph topology:
  embed_question → retrieve_chunks → assemble_context → generate_answer → extract_citations → END

Supports both streaming (SSE token-by-token) and non-streaming response modes.
LLM calls connect to the local high-speed C++ engine (llama.cpp server / OpenAI compatible API).
"""
import json
import logging
from typing import Any, AsyncGenerator, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from app.utils.chroma_client import query_collection
from app.utils.embedder import embed_single

logger = logging.getLogger(__name__)

NO_DOCS_MESSAGE = (
    "📄 **No relevant documents found in this Knowledge Space.**\n\n"
    "Please upload documents (PDF, PPTX, Video, or Audio) to this space using the sidebar. "
    "Once uploaded, I will answer your questions strictly using the information in your documents."
)


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
    """Node 1: Embed the user question using the fast ONNX embedding model."""
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
    state["context"] = "\n\n---\n\n".join(parts) if parts else ""
    return state


def _build_prompt(state: RAGState) -> str:
    """Construct the strict document-grounded prompt for the LLM."""
    history_lines: list[str] = []
    for msg in state["chat_history"][-6:]:  # last 3 turns
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior conversation)"

    return f"""You are RagVault, an expert document-grounded AI assistant.
Your task is to provide comprehensive, accurate, and direct answers to questions based ONLY on the provided context excerpts from uploaded documents.

GUIDELINES:
1. Ground your answer thoroughly in the facts, details, and explanations provided in the CONTEXT below.
2. Structure your response clearly using Markdown (bullet points, bold text, headings, or numbered steps where appropriate).
3. When presenting specific facts, reference the source like [Source: <filename>, Page: <page>].
4. If the provided context does not contain enough information to answer the question, clearly state: "I cannot find sufficient information in your uploaded documents to answer this question. Please check your uploaded files or upload additional relevant material."

=== CONTEXT FROM UPLOADED DOCUMENTS ===
{state['context']}

=== CONVERSATION HISTORY ===
{history_block}

=== USER QUESTION ===
{state['question']}

=== GROUNDED RESPONSE ==="""


def generate_answer_node(state: RAGState) -> RAGState:
    """Node 4: Call LLM with the assembled prompt (non-streaming path)."""
    from app.config import get_settings

    if not state.get("retrieved_chunks") or not state.get("context"):
        state["answer"] = NO_DOCS_MESSAGE
        return state

    cfg = get_settings()
    prompt = _build_prompt(state)

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{cfg.llm_base_url}/chat/completions",
                json={
                    "model": cfg.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            state["answer"] = answer.strip()
    except Exception as exc:
        logger.error("[RAG] LLM generation error: %s", exc)
        state["answer"] = (
            f"⚠️ **LLM Error**: Could not generate response using local LLM model `{cfg.llm_model}`.\n"
            f"Please ensure local LLM server is running at `{cfg.llm_base_url}`."
        )
    return state


def extract_citations_node(state: RAGState) -> RAGState:
    """
    Node 5: Build a deduplicated citation list from the retrieved chunk metadata.
    Citations are derived from metadata, NOT from LLM hallucination.
    """
    if not state.get("retrieved_chunks"):
        state["citations"] = []
        return state

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

    Yields lines in JSON format:
        data: {"token": "..."}\\n\\n
    Terminates with:
        data: {"citations": [...]}\\n\\n
        data: [DONE]\\n\\n
    """
    from app.config import get_settings

    cfg = get_settings()

    # ── Steps 1-2: embed → retrieve ───
    query_embedding = embed_single(question)
    retrieved_chunks = query_collection(
        chat_id=chat_id,
        query_embedding=query_embedding,
        k=cfg.top_k,
    )

    # ── Guard: If no documents or chunks exist, ask user to upload ────────────
    if not retrieved_chunks:
        yield f"data: {json.dumps({'token': NO_DOCS_MESSAGE})}\n\n"
        yield f"data: {json.dumps({'citations': []})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── Step 3: Build context block ───────────────────────────────────────────
    parts: list[str] = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        parts.append(
            f"[{i}] Source: {chunk['source']} | Page: {chunk['page']}\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(parts)

    # Build prompt
    history_lines: list[str] = []
    for msg in chat_history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior conversation)"

    prompt = f"""You are RagVault, an expert document-grounded AI assistant.
Your task is to provide comprehensive, accurate, and direct answers to questions based ONLY on the provided context excerpts from uploaded documents.

GUIDELINES:
1. Ground your answer thoroughly in the facts, details, and explanations provided in the CONTEXT below.
2. Structure your response clearly using Markdown (bullet points, bold text, headings, or numbered steps where appropriate).
3. When presenting specific facts, reference the source like [Source: <filename>, Page: <page>].
4. If the provided context does not contain enough information to answer the question, clearly state: "I cannot find sufficient information in your uploaded documents to answer this question. Please check your uploaded files or upload additional relevant material."

=== CONTEXT FROM UPLOADED DOCUMENTS ===
{context}

=== CONVERSATION HISTORY ===
{history_block}

=== USER QUESTION ===
{question}

=== GROUNDED RESPONSE ==="""

    # ── Step 4: Stream tokens from LLM with temperature=0.0 (Strict Grounding)
    logger.info("[RAG:stream] Streaming response from local LLM at %s", cfg.llm_base_url)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{cfg.llm_base_url}/chat/completions",
                json={
                    "model": cfg.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    raise RuntimeError(f"LLM returned HTTP {response.status_code}: {err_text.decode('utf-8', errors='ignore')}")

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(payload)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                        except Exception:
                            continue
    except Exception as exc:
        logger.error("[RAG:stream] LLM streaming error: %s", exc)
        err_msg = (
            f"⚠️ **LLM Model Error**: Failed to stream from LLM at `{cfg.llm_base_url}`.\n"
            f"Please ensure local LLM server is running. Error: {exc}"
        )
        yield f"data: {json.dumps({'token': err_msg})}\n\n"

    # ── Step 5: Emit deduplicated citations as metadata event ─────────────────
    seen: set[tuple[str, int]] = set()
    citations: list[dict[str, Any]] = []
    for chunk in retrieved_chunks:
        key = (chunk["source"], chunk["page"])
        if key not in seen:
            seen.add(key)
            citations.append({"source": chunk["source"], "page": chunk["page"]})

    yield f"data: {json.dumps({'citations': citations})}\n\n"
    yield "data: [DONE]\n\n"
