"""
FastAPI application entry point.
Mounts all routers, configures CORS, and handles startup/shutdown lifecycle.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.chats import router as chats_router
from app.routers.documents import router as documents_router
from app.routers.messages import router as messages_router
from app.routers.quiz import router as quiz_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    cfg = get_settings()

    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting AI Knowledge Hub API (env=%s)", cfg.environment)

    # Create temp upload directory
    os.makedirs(cfg.upload_temp_dir, exist_ok=True)
    logger.info("Upload temp dir: %s", cfg.upload_temp_dir)

    # Pre-warm embedding model (so first request isn't slow)
    try:
        from app.utils.embedder import get_embedding_model
        get_embedding_model()
        logger.info("Embedding model pre-loaded successfully")
    except Exception as exc:
        logger.warning("Failed to pre-load embedding model: %s", exc)

    # Verify ChromaDB connection
    try:
        from app.utils.chroma_client import get_chroma_client
        client = get_chroma_client()
        client.heartbeat()
        logger.info("ChromaDB connection verified")
    except Exception as exc:
        logger.warning("ChromaDB not reachable yet: %s (will retry on first request)", exc)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down AI Knowledge Hub API")


# ─── App Instance ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Knowledge Hub API",
    description=(
        "Offline RAG-based learning system. "
        "Upload PPTX, PDF, video, and audio files, then chat with your documents."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:80",
        "http://frontend",
        "http://frontend:80",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(documents_router)
app.include_router(messages_router)
app.include_router(quiz_router)


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Health check endpoint used by Docker Compose healthcheck."""
    return {"status": "ok", "version": "1.0.0"}
