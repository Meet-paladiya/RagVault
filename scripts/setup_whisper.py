"""
Standalone Whisper Model Downloader for RagVault.
Downloads the 4 required CTranslate2 files for Systran/faster-whisper-base (~148 MB total)
with resume capability, timeout handling, and automatic mirror fallback.
Places files in both `./models/whisper-base` and `./backend/models/whisper-base`
so both local host and Docker containers run 100% offline.
"""
import os
import sys
import time
import urllib.request
import urllib.error

# Files that comprise Systran/faster-whisper-base
WHISPER_FILES = {
    "config.json": 2300,            # ~2.3 KB
    "model.bin": 145000000,         # ~145 MB
    "tokenizer.json": 2200000,      # ~2.2 MB
    "vocabulary.txt": 460000,       # ~460 KB
}

REPO_ID = "Systran/faster-whisper-base"
PRIMARY_URL_BASE = f"https://huggingface.co/{REPO_ID}/resolve/main"
MIRROR_URL_BASE = f"https://hf-mirror.com/{REPO_ID}/resolve/main"


def download_single_file(filename: str, expected_size: int, target_dirs: list[str], max_retries: int = 5) -> bool:
    """Download a single model file to multiple target directories with resume support."""
    # Check if primary target already has the valid file
    first_target = os.path.join(target_dirs[0], filename)
    if os.path.exists(first_target) and os.path.getsize(first_target) >= int(expected_size * 0.95):
        print(f"  [OK] {filename} already present ({os.path.getsize(first_target) / (1024*1024):.2f} MB)")
        # Copy to any other target dirs that don't have it
        _sync_to_dirs(first_target, filename, target_dirs[1:])
        return True

    temp_path = first_target + ".part"
    os.makedirs(os.path.dirname(first_target), exist_ok=True)

    urls = [
        f"{PRIMARY_URL_BASE}/{filename}",
        f"{MIRROR_URL_BASE}/{filename}",
    ]

    for attempt in range(1, max_retries + 1):
        url = urls[(attempt - 1) % len(urls)]
        downloaded = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0

        headers = {"User-Agent": "RagVaultWhisperDownloader/1.0"}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            print(f"  Resuming {filename} from {downloaded / (1024*1024):.2f} MB (attempt {attempt}/{max_retries})...")
        else:
            print(f"  Downloading {filename} (attempt {attempt}/{max_retries}) from {url.split('/')[2]}...")

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                mode = "ab" if downloaded > 0 else "wb"
                with open(temp_path, mode) as f:
                    chunk_size = 512 * 1024  # 512 KB
                    last_print = time.time()
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_print > 0.5:
                            mb_down = downloaded / (1024 * 1024)
                            mb_exp = expected_size / (1024 * 1024)
                            pct = min(100.0, (downloaded / expected_size) * 100) if expected_size > 0 else 0
                            sys.stdout.write(f"\r    -> {filename}: {mb_down:.1f} MB / {mb_exp:.1f} MB [{pct:.1f}%]")
                            sys.stdout.flush()
                            last_print = now

            if os.path.exists(temp_path) and os.path.getsize(temp_path) >= int(expected_size * 0.95):
                if os.path.exists(first_target):
                    os.unlink(first_target)
                os.replace(temp_path, first_target)
                print(f"\n  [OK] Successfully saved {filename} ({os.path.getsize(first_target) / (1024*1024):.2f} MB)")
                _sync_to_dirs(first_target, filename, target_dirs[1:])
                return True

        except Exception as exc:
            print(f"\n  [Notice attempt {attempt}]: {exc}. Retrying...")
            time.sleep(2)

    if os.path.exists(temp_path) and os.path.getsize(temp_path) >= int(expected_size * 0.95):
        os.replace(temp_path, first_target)
        _sync_to_dirs(first_target, filename, target_dirs[1:])
        return True

    return False


def _sync_to_dirs(source_file: str, filename: str, target_dirs: list[str]):
    """Copy verified file to other destination directories."""
    import shutil
    for d in target_dirs:
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, filename)
        if not os.path.exists(dest) or os.path.getsize(dest) != os.path.getsize(source_file):
            try:
                shutil.copy2(source_file, dest)
            except Exception as e:
                print(f"  Warning copying {filename} to {dest}: {e}")


def setup_whisper():
    """Ensure all 4 Whisper files exist locally."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dirs = [
        os.path.join(root_dir, "models", "whisper-base"),
        os.path.join(root_dir, "backend", "models", "whisper-base"),
    ]
    # Also support container path /models if running inside Docker
    if os.path.exists("/models"):
        target_dirs.insert(0, "/models/whisper-base")

    print("\n" + "=" * 60)
    print(" RagVault — Offline Whisper Speech-to-Text Model Downloader")
    print(f" Target directories:\n  - " + "\n  - ".join(target_dirs))
    print("=" * 60)

    all_ok = True
    for filename, expected_size in WHISPER_FILES.items():
        ok = download_single_file(filename, expected_size, target_dirs)
        if not ok:
            all_ok = False
            print(f"  [ERROR] Failed to download {filename}!")

    if all_ok:
        print("\n[SUCCESS] Faster-Whisper base model is completely downloaded and ready for offline use!")
        return True
    else:
        print("\n[WARNING] Some model files could not be downloaded. Check internet connection and rerun.")
        return False


if __name__ == "__main__":
    success = setup_whisper()
    sys.exit(0 if success else 1)
