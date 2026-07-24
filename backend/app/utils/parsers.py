from typing import List, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".pptx",
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

def parse_file(path: str) -> List[Dict[str, Any]]:
    """Dispatch to the right parser based on extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext == ".pptx":
        return parse_pptx(path)
    elif ext in AUDIO_EXTENSIONS:
        return parse_audio(path)
    elif ext in VIDEO_EXTENSIONS:
        return parse_video(path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def parse_pdf(path: str) -> List[Dict[str, Any]]:
    """PyMuPDF page-by-page extraction."""
    import fitz
    logger.info(f"Parsing PDF: {path}")
    doc = fitz.open(path)
    pages = []
    source = os.path.basename(path)
    for i in range(len(doc)):
        page = doc.load_page(i)
        text = page.get_text()
        if text.strip():
            pages.append({
                "text": text.strip(),
                "page": i + 1,
                "source": source
            })
    return pages

def parse_pptx(path: str) -> List[Dict[str, Any]]:
    """python-pptx slide-by-slide text extraction."""
    from pptx import Presentation
    logger.info(f"Parsing PPTX: {path}")
    prs = Presentation(path)
    pages = []
    source = os.path.basename(path)
    for i, slide in enumerate(prs.slides):
        text = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text.append(shape.text)
        slide_text = "\n".join(text).strip()
        if slide_text:
            pages.append({
                "text": slide_text,
                "page": i + 1,
                "source": source
            })
    return pages

def _transcribe_with_whisper(audio_path: str, source: str) -> List[Dict[str, Any]]:
    """Faster-Whisper transcription. Returns segments grouped as pages."""
    from faster_whisper import WhisperModel
    from app.config import get_settings
    settings = get_settings()
    logger.info(f"Transcribing {audio_path} using Whisper ({settings.whisper_model})")
    
    model = WhisperModel(settings.whisper_model, device=settings.whisper_device, compute_type="int8")
    segments, _ = model.transcribe(audio_path, beam_size=5)
    
    pages = []
    current_text = []
    current_page = 1
    # Group every ~30 seconds of speech into one "page"
    page_duration = 30.0
    start_time = 0.0

    for segment in segments:
        current_text.append(segment.text)
        if segment.end - start_time >= page_duration:
            pages.append({
                "text": " ".join(current_text).strip(),
                "page": current_page,
                "source": source
            })
            current_text = []
            current_page += 1
            start_time = segment.end

    if current_text:
        pages.append({
            "text": " ".join(current_text).strip(),
            "page": current_page,
            "source": source
        })

    return pages

def parse_audio(path: str) -> List[Dict[str, Any]]:
    source = os.path.basename(path)
    return _transcribe_with_whisper(path, source)

def parse_video(path: str) -> List[Dict[str, Any]]:
    """Extract audio with ffmpeg then transcribe."""
    import subprocess, tempfile
    source = os.path.basename(path)
    logger.info(f"Extracting audio from video: {path}")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
        
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path],
            check=True, capture_output=True
        )
        return _transcribe_with_whisper(audio_path, source)
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)
