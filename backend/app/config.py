"""
Application settings loaded from environment variables.
All values can be overridden via .env file or environment variables.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DB_URL = "postgresql+asyncpg://knowledge_user:changeme_strong_password@postgres:5432/knowledge_hub"

class Settings(BaseSettings):
    # ── PostgreSQL ────────────────────────────────────────────────────────────
    database_url: str = _DEFAULT_DB_URL

    # ── JWT Auth ──────────────────────────────────────────────────────────────
    jwt_secret: str = "change_this_to_a_long_random_secret_key_at_least_32_chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # ── Ollama (Local LLM) ───────────────────────────────────────────────────
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:1.5b-instruct"

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_fallback_model: str = "nomic-embed-text"

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_persist_dir: str = "/chroma_data"

    # ── File Storage ──────────────────────────────────────────────────────────
    upload_temp_dir: str = "/uploads/temp"

    # ── RAG / Chunking ────────────────────────────────────────────────────────
    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 5

    # ── Faster-Whisper ────────────────────────────────────────────────────────
    whisper_model: str = "base"
    whisper_device: str = "cpu"

    # ── Runtime ───────────────────────────────────────────────────────────────
    environment: str = "production"
    log_level: str = "INFO"

    # ── HuggingFace Cache ─────────────────────────────────────────────────────
    hf_home: str = "/hf_cache"

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return _DEFAULT_DB_URL
        return str(v)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return singleton Settings instance (cached after first call)."""
    return Settings()
