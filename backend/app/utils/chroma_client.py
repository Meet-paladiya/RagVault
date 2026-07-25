"""
ChromaDB HTTP client wrapper.
Provides collection management, chunk storage, querying, and deletion.
All calls go to the ChromaDB HTTP server running in Docker.
"""
import logging
from functools import lru_cache
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.ClientAPI:
    """
    Return a ChromaDB client.
    Tries HTTP server first if running in Docker with standalone Chroma container.
    Falls back to embedded PersistentClient if HTTP server is not reachable.
    """
    from app.config import get_settings

    cfg = get_settings()
    try:
        logger.info("Connecting to ChromaDB HTTP server at %s:%s", cfg.chroma_host, cfg.chroma_port)
        client = chromadb.HttpClient(
            host=cfg.chroma_host,
            port=cfg.chroma_port,
            settings=Settings(anonymized_telemetry=False),
        )
        client.heartbeat()
        logger.info("Successfully connected to ChromaDB HTTP server.")
        return client
    except Exception as exc:
        logger.warning(
            "Could not connect to ChromaDB HTTP server (%s). Using embedded PersistentClient at %s",
            exc,
            cfg.chroma_persist_dir,
        )
        return chromadb.PersistentClient(
            path=cfg.chroma_persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )


def _collection_name(chat_id: str) -> str:
    """Derive a valid ChromaDB collection name from a chat UUID."""
    # ChromaDB collection names must match [a-zA-Z0-9_-]{3,63}
    return f"chat_{chat_id.replace('-', '_')}"


def get_or_create_collection(chat_id: str) -> chromadb.Collection:
    """Return (or create) the ChromaDB collection for a given chat_id."""
    client = get_chroma_client()
    name = _collection_name(chat_id)
    collection = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
    logger.debug("Using collection: %s", name)
    return collection


def add_chunks_to_collection(
    chat_id: str,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    document_id: str,
) -> None:
    """
    Upsert document chunks into the chat's ChromaDB collection.
    Accumulates knowledge — does NOT replace existing chunks.

    Args:
        chat_id:     The UUID of the chat (knowledge space).
        chunks:      List of dicts with keys: text, page, source, chunk_index.
        embeddings:  Parallel list of embedding vectors.
        document_id: UUID of the parent document (used for per-doc deletion).
    """
    collection = get_or_create_collection(chat_id)

    ids = [f"{document_id}_{chunk['chunk_index']}" for chunk in chunks]
    metadatas: list[dict[str, Any]] = [
        {
            "chat_id": chat_id,
            "document_id": document_id,
            "source": chunk["source"],
            "page": int(chunk["page"]),
            "chunk_index": int(chunk["chunk_index"]),
        }
        for chunk in chunks
    ]
    documents = [chunk["text"] for chunk in chunks]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )
    logger.info(
        "Upserted %d chunks into collection %s (document_id=%s)",
        len(chunks),
        _collection_name(chat_id),
        document_id,
    )


def query_collection(
    chat_id: str,
    query_embedding: list[float],
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Retrieve the top-k most similar chunks for a query embedding.

    Returns:
        List of dicts: {text, source, page, chunk_index, document_id, distance}
    """
    collection = get_or_create_collection(chat_id)

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed (empty collection?): %s", exc)
        return []

    hits: list[dict[str, Any]] = []
    docs = results.get("documents", [[]])[0] or []
    metas = results.get("metadatas", [[]])[0] or []
    dists = results.get("distances", [[]])[0] or []

    for doc_text, meta, dist in zip(docs, metas, dists):
        hits.append(
            {
                "text": doc_text,
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", 0),
                "chunk_index": meta.get("chunk_index", 0),
                "document_id": meta.get("document_id", ""),
                "distance": float(dist),
            }
        )
    return hits


def delete_collection(chat_id: str) -> None:
    """Delete the entire ChromaDB collection for a chat (clear knowledge)."""
    client = get_chroma_client()
    name = _collection_name(chat_id)
    try:
        client.delete_collection(name)
        logger.info("Deleted ChromaDB collection: %s", name)
    except Exception as exc:
        logger.warning("Collection %s not found or already deleted: %s", name, exc)


def delete_document_chunks(chat_id: str, document_id: str) -> None:
    """Remove all chunks belonging to a specific document from the collection."""
    collection = get_or_create_collection(chat_id)
    try:
        collection.delete(where={"document_id": {"$eq": document_id}})
        logger.info(
            "Deleted chunks for document_id=%s from collection %s",
            document_id,
            _collection_name(chat_id),
        )
    except Exception as exc:
        logger.warning("Failed to delete chunks for document %s: %s", document_id, exc)


def get_all_chunks(chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve chunks from the chat's collection without query embeddings."""
    collection = get_or_create_collection(chat_id)
    try:
        results = collection.get(
            limit=limit,
            include=["documents", "metadatas"],
        )
    except Exception as exc:
        logger.warning("ChromaDB get failed: %s", exc)
        return []

    hits: list[dict[str, Any]] = []
    docs = results.get("documents") or []
    metas = results.get("metadatas") or []

    for doc_text, meta in zip(docs, metas):
        hits.append(
            {
                "text": doc_text,
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", 0),
                "chunk_index": meta.get("chunk_index", 0),
                "document_id": meta.get("document_id", ""),
            }
        )
    return hits
