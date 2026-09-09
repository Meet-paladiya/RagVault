"""
Offline Model Setup Script for RagVault.
Downloads the quantized GGUF model for llama.cpp server with automatic resume and retry support.
Works both on host and inside Docker container.
"""
import os
import sys
import time
import urllib.request
import urllib.error

# Support container path (/models), environment variable, or host workspace path
MODEL_DIR = os.environ.get("MODEL_DIR") or (
    "/models" if os.path.exists("/models") else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
)
MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILENAME)
MODEL_URL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"


def download_with_resume(url: str, dest_path: str, max_retries: int = 10):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    temp_path = dest_path + ".part"

    total_size = 1117320736  # ~1.06 GB known size for qwen2.5-1.5b-instruct-q4_k_m.gguf

    if os.path.exists(dest_path) and os.path.getsize(dest_path) >= total_size - 1024:
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f"[OK] Model already fully present at: {dest_path} ({size_mb:.1f} MB)")
        return dest_path

    # Try fetching Content-Length if possible
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RagVaultDownloader/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_len = resp.headers.get("Content-Length")
            if content_len:
                total_size = int(content_len)
    except Exception:
        pass

    for attempt in range(1, max_retries + 1):
        downloaded = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0

        if downloaded >= total_size:
            os.replace(temp_path, dest_path)
            print(f"\n[OK] Model successfully verified at {dest_path}")
            return dest_path

        headers = {"User-Agent": "RagVaultDownloader/1.0"}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            print(f"\nResuming model download from {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB [Attempt {attempt}/{max_retries}]...")
        else:
            print(f"Downloading {MODEL_FILENAME} ({total_size / (1024 * 1024):.1f} MB) [Attempt {attempt}/{max_retries}]...")

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                mode = "ab" if downloaded > 0 else "wb"
                with open(temp_path, mode) as f:
                    chunk_size = 1024 * 1024  # 1 MB
                    last_print = time.time()
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_print > 0.5:
                            percent = min(100.0, downloaded * 100.0 / total_size)
                            mb_down = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            sys.stdout.write(f"\rDownloading {MODEL_FILENAME}: {mb_down:.1f} MB / {mb_total:.1f} MB [{percent:.1f}%]")
                            sys.stdout.flush()
                            last_print = now

            if downloaded >= total_size - 1024:
                os.replace(temp_path, dest_path)
                print(f"\n[OK] Model download complete! Saved to: {dest_path}")
                return dest_path

        except Exception as exc:
            print(f"\n[Attempt {attempt} connection notice]: {exc}. Retrying in 3 seconds...")
            time.sleep(3)

    if os.path.exists(temp_path) and os.path.getsize(temp_path) >= total_size - 1024:
        os.replace(temp_path, dest_path)
        return dest_path

    raise RuntimeError(f"Failed to download model after {max_retries} attempts.")


def ensure_model():
    return download_with_resume(MODEL_URL, MODEL_PATH)


if __name__ == "__main__":
    ensure_model()
