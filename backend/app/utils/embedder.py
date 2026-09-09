"""
FastEmbed (ONNX Runtime) embedding wrapper.
Loads BAAI/bge-small-en-v1.5 (or configured model) as a singleton
and provides high-speed batch + single-text embedding functions without PyTorch overhead.
"""
import logging
from functools import lru_cache
from typing import Any

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    """
    Load and cache the FastEmbed ONNX embedding model.
    Called once at startup / first embed; subsequent calls return the cached instance.
    Model weights are downloaded on first run to cache_dir, then loaded locally offline.
    """
    from app.config import get_settings

    cfg = get_settings()
    logger.info("Loading FastEmbed embedding model: %s", cfg.embedding_model)
    model = TextEmbedding(
        model_name=cfg.embedding_model,
        cache_dir=cfg.hf_home,
    )
    logger.info("FastEmbed embedding model loaded successfully: %s", cfg.embedding_model)
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts using FastEmbed (ONNX Runtime).

    Args:
        texts: List of strings to embed.

    Returns:
        List of float vectors (L2-normalized cosine embeddings).
    """
    if not texts:
        return []

    model = get_embedding_model()
    # model.embed returns a generator of numpy ndarrays
    embeddings = list(model.embed(texts))
    return [vec.tolist() for vec in embeddings]


def embed_single(text: str) -> list[float]:
    """Embed a single string. Convenience wrapper around embed_texts."""
    return embed_texts([text])[0]
