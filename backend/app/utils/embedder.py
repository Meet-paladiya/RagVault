"""
SentenceTransformers embedding wrapper.
Loads BAAI/bge-base-en-v1.5 (or configured model) as a singleton
and provides batch + single-text embedding functions.
"""
import logging
from functools import lru_cache
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """
    Load and cache the SentenceTransformer embedding model.
    Called once at startup; subsequent calls return the cached instance.
    Model is downloaded to HF_HOME on first run, then used offline.
    """
    from app.config import get_settings

    cfg = get_settings()
    logger.info("Loading embedding model: %s", cfg.embedding_model)
    model = SentenceTransformer(cfg.embedding_model)
    logger.info("Embedding model loaded. Dimension: %d", model.get_sentence_embedding_dimension())
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts.

    Args:
        texts: List of strings to embed.

    Returns:
        List of float vectors (L2-normalised cosine embeddings).
    """
    if not texts:
        return []

    model = get_embedding_model()
    # normalize_embeddings=True → unit-norm vectors → cosine sim = dot product
    embeddings: np.ndarray = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def embed_single(text: str) -> list[float]:
    """Embed a single string. Convenience wrapper around embed_texts."""
    return embed_texts([text])[0]
