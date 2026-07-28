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
from app.database import create_tables
from app.routers.auth import router as auth_router
from app.routers.chats import router as chats_router
from app.routers.documents import router as documents_router
from app.routers.messages import router as messages_router
from app.routers.quiz import router as quiz_router
from app.routers.notes import router as notes_router

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
    logger.info("Starting RagVault API (env=%s)", cfg.environment)

    # Create database tables
    await create_tables()
    logger.info("Database tables initialized successfully.")

    # Create temp upload directory
    os.makedirs(cfg.upload_temp_dir, exist_ok=True)
    logger.info("Upload temp dir: %s", cfg.upload_temp_dir)

    # NOTE: Embedding model and ChromaDB load lazily on first request.
    logger.info("API startup complete — ready to accept requests.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down RagVault API")


# ─── App Instance ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="RagVault API",
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
app.include_router(notes_router)


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Health check endpoint used by Docker Compose healthcheck."""
    return {"status": "ok", "version": "1.0.0"}
