"""
Ollama helper functions for model verification and automatic pull triggering.
"""
import logging
import httpx

logger = logging.getLogger(__name__)


async def check_and_pull_ollama_model() -> bool:
    """
    Check if configured OLLAMA_MODEL is available in the local Ollama instance.
    If not found, log warning and attempt background pull via Ollama HTTP API.

    Returns:
        True if model is present or pull successfully triggered, False otherwise.
    """
    from app.config import get_settings

    cfg = get_settings()
    base_url = cfg.ollama_base_url.rstrip("/")
    target_model = cfg.ollama_model

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check exact match or model prefix (e.g. qwen2.5:1.5b-instruct vs qwen2.5:1.5b-instruct:latest)
                model_exists = any(
                    target_model in m or m in target_model
                    for m in models
                )
                if model_exists:
                    logger.info("[OLLAMA] Model '%s' is present and ready.", target_model)
                    return True
                
                logger.warning(
                    "[OLLAMA] Model '%s' not found in installed models %s. Attempting auto-pull...",
                    target_model,
                    models,
                )

                # Attempt pull request
                pull_resp = await client.post(
                    f"{base_url}/api/pull",
                    json={"name": target_model, "stream": False},
                    timeout=300.0,
                )
                if pull_resp.status_code == 200:
                    logger.info("[OLLAMA] Successfully pulled model '%s'.", target_model)
                    return True
                else:
                    logger.error(
                        "[OLLAMA] Auto-pull failed with status %d: %s. Run `docker exec hub_ollama ollama pull %s`",
                        pull_resp.status_code,
                        pull_resp.text,
                        target_model,
                    )
                    return False
    except Exception as exc:
        logger.warning("[OLLAMA] Could not connect to Ollama at %s: %s", base_url, exc)
        return False
