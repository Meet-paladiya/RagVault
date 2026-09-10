"""Serialize local Ollama work on CPU-only machines."""
import asyncio


ollama_generation_gate = asyncio.Semaphore(1)
