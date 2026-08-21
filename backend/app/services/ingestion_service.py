"""
Document ingestion service.
Pipeline: validate → save temp → parse → chunk → embed → store in ChromaDB → cleanup.
CPU-heavy steps run in a ThreadPoolExecutor to avoid blocking the async event loop.
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.utils.chroma_client import add_chunks_to_collection
from app.utils.chunker import chunk_pages
from app.utils.embedder import embed_texts
from app.utils.parsers import SUPPORTED_EXTENSIONS, parse_file

logger = logging.getLogger(__name__)

# One shared executor for CPU-bound work (parsing + embedding)
_executor = ThreadPoolExecutor(max_workers=2)


def _validate_extension(filename: str) -> str:
    """Return the lowercased extension or raise ValueError for unsupported types."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"File type '{ext}' is not supported. "
            f"Accepted types: PDF, PPTX, TXT, MD, DOCX, MP4/MKV/MOV/AVI/WEBM, MP3/WAV/M4A/OGG/FLAC/AAC."
        )
    return ext


def _sync_ingest_pipeline(
    file_path: str,
    filename: str,
    chat_id: str,
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
) -> dict:
    """
    Synchronous ingestion steps (run in a thread pool):
      1. Parse file → list of pages
      2. Chunk pages → list of chunks
      3. Embed chunks → list of vectors
      4. Upsert into ChromaDB

    Returns stats dict: {total_pages, total_chunks}
    """
    logger.info("[INGEST] Parsing %s (document_id=%s)", filename, document_id)
    pages = parse_file(file_path)
    for p in pages:
        p["source"] = filename
    total_pages = len(pages)
    logger.info("[INGEST] Extracted %d pages from %s", total_pages, filename)

    chunks = chunk_pages(pages, chunk_size=chunk_size, overlap=chunk_overlap)
    total_chunks = len(chunks)
    logger.info("[INGEST] Created %d chunks from %s", total_chunks, filename)

    if chunks:
        texts = [c["text"] for c in chunks]
        logger.info("[INGEST] Embedding %d chunks...", total_chunks)
        embeddings = embed_texts(texts)
        logger.info("[INGEST] Storing chunks in ChromaDB collection chat_%s", chat_id)
        add_chunks_to_collection(chat_id, chunks, embeddings, document_id)

    return {"total_pages": total_pages, "total_chunks": total_chunks}


async def ingest_document(
    db: AsyncSession,
    chat_id: str,
    file_path: str,
    filename: str,
    document_id: str,
) -> Document:
    """
    Full asynchronous ingestion pipeline.

    1. Validate file extension (reject DOCX, images, etc.)
    2. Run CPU-heavy parse → chunk → embed → store in a thread pool
    3. Update the Document row with results
    4. Delete the temporary file
    5. Return the updated Document record

    On any failure: set status='failed', delete temp file, re-raise.
    """
    from app.config import get_settings

    cfg = get_settings()

    # ── Step 1: Validate extension ────────────────────────────────────────────
    try:
        _validate_extension(filename)
    except ValueError as exc:
        logger.error("[INGEST] Rejected file %s: %s", filename, exc)
        raise

    # ── Step 2: Fetch the Document record ─────────────────────────────────────
    result = await db.execute(
        select(Document).where(Document.id == UUID(document_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise RuntimeError(f"Document record not found: {document_id}")

    try:
        # ── Step 3: Run pipeline in thread pool ───────────────────────────────
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(
            _executor,
            _sync_ingest_pipeline,
            file_path,
            filename,
            chat_id,
            document_id,
            cfg.chunk_size,
            cfg.chunk_overlap,
        )

        # ── Step 4: Update DB record ──────────────────────────────────────────
        doc.total_pages = stats["total_pages"]
        doc.total_chunks = stats["total_chunks"]
        doc.status = "processed"
        await db.commit()
        await db.refresh(doc)
        logger.info(
            "[INGEST] Completed %s: %d pages, %d chunks",
            filename,
            stats["total_pages"],
            stats["total_chunks"],
        )

    except Exception as exc:
        logger.exception("[INGEST] Failed to ingest %s: %s", filename, exc)
        doc.status = "failed"
        await db.commit()
        raise

    finally:
        # ── Step 5: Delete the temp file (always) ────────────────────────────
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug("[INGEST] Deleted temp file: %s", file_path)

    return doc
