"""
Token-aware text chunker using tiktoken (cl100k_base encoding).
Splits document pages into overlapping chunks of ~chunk_size tokens,
preferring sentence boundaries when possible.
"""
import logging
import re
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_into_sentences(text: str) -> list[str]:
    """
    Naïve sentence splitter. Falls back gracefully on edge cases.
    Splits on '. ', '! ', '? ', '\n\n' boundaries.
    """
    # Split on sentence-ending punctuation followed by whitespace or newline
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_pages(
    pages: list[dict[str, Any]],
    chunk_size: int = 600,
    overlap: int = 100,
) -> list[dict[str, Any]]:
    """
    Chunk a list of parsed document pages into overlapping token windows.

    Args:
        pages:      Output of parsers.parse_file() — list of {text, page, source}.
        chunk_size: Target maximum tokens per chunk.
        overlap:    Number of tokens to carry over between consecutive chunks.

    Returns:
        List of dicts: {text, page, source, chunk_index, token_count}.
    """
    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    for page_obj in pages:
        page_text: str = page_obj["text"]
        page_num: int = page_obj["page"]
        source: str = page_obj["source"]

        if not page_text.strip():
            continue

        sentences = _split_into_sentences(page_text)
        if not sentences:
            continue

        current_sentences: list[str] = []
        current_tokens: int = 0

        for sentence in sentences:
            s_tokens = _count_tokens(sentence)

            # If a single sentence exceeds chunk_size, force-split it by tokens
            if s_tokens > chunk_size:
                # Flush current buffer first
                if current_sentences:
                    chunk_text = " ".join(current_sentences)
                    chunks.append(
                        {
                            "text": chunk_text,
                            "page": page_num,
                            "source": source,
                            "chunk_index": chunk_index,
                            "token_count": _count_tokens(chunk_text),
                        }
                    )
                    chunk_index += 1
                    current_sentences = []
                    current_tokens = 0

                # Hard-split the long sentence at token boundaries
                token_ids = _ENCODING.encode(sentence)
                start = 0
                while start < len(token_ids):
                    end = min(start + chunk_size, len(token_ids))
                    sub_text = _ENCODING.decode(token_ids[start:end])
                    chunks.append(
                        {
                            "text": sub_text,
                            "page": page_num,
                            "source": source,
                            "chunk_index": chunk_index,
                            "token_count": end - start,
                        }
                    )
                    chunk_index += 1
                    start += chunk_size - overlap
                continue

            # Would adding this sentence exceed the target size?
            if current_tokens + s_tokens > chunk_size and current_sentences:
                chunk_text = " ".join(current_sentences)
                chunks.append(
                    {
                        "text": chunk_text,
                        "page": page_num,
                        "source": source,
                        "chunk_index": chunk_index,
                        "token_count": _count_tokens(chunk_text),
                    }
                )
                chunk_index += 1

                # Carry over overlap: take trailing sentences summing to ≤ overlap tokens
                overlap_sentences: list[str] = []
                overlap_tokens = 0
                for prev_sentence in reversed(current_sentences):
                    pt = _count_tokens(prev_sentence)
                    if overlap_tokens + pt > overlap:
                        break
                    overlap_sentences.insert(0, prev_sentence)
                    overlap_tokens += pt

                current_sentences = overlap_sentences
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_tokens += s_tokens

        # Flush any remaining sentences for this page
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(
                {
                    "text": chunk_text,
                    "page": page_num,
                    "source": source,
                    "chunk_index": chunk_index,
                    "token_count": _count_tokens(chunk_text),
                }
            )
            chunk_index += 1

    logger.info("Chunked %d pages into %d chunks", len(pages), len(chunks))
    return chunks
