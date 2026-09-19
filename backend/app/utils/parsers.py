from typing import List, Dict, Any
import logging
import os
import threading

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".pptx", ".ppt", ".txt", ".md", ".docx", ".doc",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff",
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"
}

TEXT_EXTENSIONS = {".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

def parse_file(path: str) -> List[Dict[str, Any]]:
    """Dispatch to the right parser based on extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext in {".pptx", ".ppt"}:
        return parse_pptx(path)
    elif ext in TEXT_EXTENSIONS:
        return parse_text(path)
    elif ext in {".docx", ".doc"}:
        return parse_docx(path)
    elif ext in IMAGE_EXTENSIONS:
        return parse_image(path)
    elif ext in AUDIO_EXTENSIONS:
        return parse_audio(path)
    elif ext in VIDEO_EXTENSIONS:
        return parse_video(path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def parse_text(path: str) -> List[Dict[str, Any]]:
    """Plain text or Markdown file extraction."""
    logger.info(f"Parsing text/markdown: {path}")
    source = os.path.basename(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return []

    # If text is long, break it into pseudo-pages of ~2000 characters
    page_size = 2000
    pages = []
    lines = content.splitlines(keepends=True)
    current_page_text = []
    current_len = 0
    page_num = 1

    for line in lines:
        current_page_text.append(line)
        current_len += len(line)
        if current_len >= page_size:
            text = "".join(current_page_text).strip()
            if text:
                pages.append({"text": text, "page": page_num, "source": source})
                page_num += 1
            current_page_text = []
            current_len = 0

    if current_page_text:
        text = "".join(current_page_text).strip()
        if text:
            pages.append({"text": text, "page": page_num, "source": source})

    return pages

def parse_docx(path: str) -> List[Dict[str, Any]]:
    """Extract text from Word .docx file using python-docx or zipfile XML fallback."""
    logger.info(f"Parsing DOCX: {path}")
    source = os.path.basename(path)
    try:
        import docx
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paragraphs)
    except Exception:
        # Fallback to direct XML extraction from docx zip
        import zipfile
        import xml.etree.ElementTree as ET
        full_text = ""
        try:
            with zipfile.ZipFile(path) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                text_elements = [elem.text for elem in tree.iter() if elem.text]
                full_text = " ".join(text_elements)
        except Exception as exc:
            logger.error(f"Failed to parse docx {path}: {exc}")

    if not full_text.strip():
        return []

    # Break into pseudo-pages
    page_size = 2000
    pages = []
    chunks = [full_text[i:i + page_size] for i in range(0, len(full_text), page_size)]
    for i, c in enumerate(chunks, start=1):
        if c.strip():
            pages.append({"text": c.strip(), "page": i, "source": source})
    return pages

def parse_pdf(path: str) -> List[Dict[str, Any]]:
    """
    Hybrid PDF parser.

    Strategy:
    1. Try normal PyMuPDF text extraction first.
    2. Decide whether the page contains meaningful digital text.
    3. If the page looks scanned/image-based, run OCR.
    4. OCR is performed only when necessary.
    5. Supports mixed PDFs containing both digital and scanned pages.

    This keeps normal PDFs fast while allowing scanned PDFs
    to enter the existing chunking/embedding pipeline.
    """

    import fitz
    try:
        import pytesseract
        from PIL import Image
        HAS_PYTESSERACT = True
    except ImportError:
        pytesseract = None
        Image = None
        HAS_PYTESSERACT = False
        logger.warning("[PDF] pytesseract or PIL is not installed; OCR fallback disabled.")

    logger.info("[PDF] Parsing PDF: %s", path)

    doc = fitz.open(path)
    pages = []
    source = os.path.basename(path)

    # -----------------------------
    # Helper: meaningful text check
    # -----------------------------
    def has_meaningful_text(text: str) -> bool:
        """
        Determine whether extracted PDF text is substantial enough
        to trust as real page content.

        We intentionally don't use a tiny fixed character threshold.
        A page with a short heading can be legitimate text.
        """

        if not text:
            return False

        cleaned = " ".join(text.split())

        # Count useful characters.
        alphanumeric_count = sum(
            char.isalnum()
            for char in cleaned
        )

        # Count words.
        words = cleaned.split()

        # Digital page is considered meaningful if:
        # - it has enough words, OR
        # - it contains a reasonable amount of actual text.
        return (
            len(words) >= 5
            or alphanumeric_count >= 40
        )

    # -----------------------------
    # Helper: detect large images
    # -----------------------------
    def has_large_image(page) -> bool:
        """
        Detect whether a page contains a large image.

        Scanned PDF pages are commonly stored as one large image
        covering most of the page.
        """

        try:
            page_area = abs(page.rect)

            if page_area <= 0:
                return False

            image_infos = page.get_image_info()

            for image_info in image_infos:
                bbox = image_info.get("bbox")

                if not bbox:
                    continue

                image_rect = fitz.Rect(bbox)

                image_area = abs(image_rect)

                coverage = image_area / page_area

                # Large image covering most of the page
                if coverage >= 0.50:
                    return True

        except Exception as exc:
            logger.warning(
                "[PDF] Image detection failed on page %d: %s",
                page.number + 1,
                exc,
            )

        return False

    # -----------------------------
    # Helper: perform OCR
    # -----------------------------
    def ocr_page(page) -> str:
        """
        Render the PDF page and run local Tesseract OCR.

        200 DPI gives a good speed/accuracy balance for
        normal scanned documents.
        """
        if not HAS_PYTESSERACT or Image is None or pytesseract is None:
            logger.warning("[PDF] Skipping OCR for scanned page: pytesseract module is not available.")
            return ""

        pix = page.get_pixmap(
            dpi=200,
            alpha=False
        )

        image = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        text = pytesseract.image_to_string(
            image,
            lang="eng",
            config="--psm 3",
        )

        return text.strip()

    # -----------------------------
    # Process pages
    # -----------------------------
    for i in range(len(doc)):

        page = doc.load_page(i)

        # ---------------------------------
        # Step 1: normal PDF text extraction
        # ---------------------------------
        extracted_text = page.get_text("text").strip()

        meaningful_text = has_meaningful_text(
            extracted_text
        )

        # ---------------------------------
        # Step 2: inspect image content
        # ---------------------------------
        large_image = has_large_image(page)

        # ---------------------------------
        # Step 3: decide whether OCR needed
        # ---------------------------------

        if meaningful_text and not large_image:
            # Normal digital PDF
            text = extracted_text

            logger.debug(
                "[PDF] Page %d: digital text extraction",
                i + 1,
            )

        elif meaningful_text and large_image:
            # Important case:
            #
            # Some PDFs contain a scanned image AND
            # a hidden OCR/text layer.
            #
            # Prefer the existing digital text because
            # it is faster and usually cleaner.
            text = extracted_text

            logger.debug(
                "[PDF] Page %d: text + image detected; "
                "using existing text layer",
                i + 1,
            )

        elif large_image:
            # No useful text + large image
            # => very likely scanned page.
            logger.info(
                "[OCR] Page %d appears to be scanned. "
                "Running OCR...",
                i + 1,
            )

            try:
                text = ocr_page(page)

                logger.info(
                    "[OCR] Page %d: extracted %d characters",
                    i + 1,
                    len(text),
                )

            except Exception as exc:
                logger.exception(
                    "[OCR] Failed on page %d: %s",
                    i + 1,
                    exc,
                )
                text = ""

        else:
            # No meaningful text and no large image.
            #
            # Could be:
            # - blank page
            # - vector-based PDF
            # - unusual PDF structure
            #
            # We don't OCR automatically because that would
            # unnecessarily slow down many normal PDFs.
            logger.debug(
                "[PDF] Page %d: no meaningful text/image; "
                "skipping OCR",
                i + 1,
            )

            text = ""

        # ---------------------------------
        # Step 4: add page to pipeline
        # ---------------------------------
        if text.strip():

            pages.append({
                "text": text.strip(),
                "page": i + 1,
                "source": source,
            })

    doc.close()

    logger.info(
        "[PDF] Completed parsing: %d pages extracted from %s",
        len(pages),
        source,
    )

    return pages

def _extract_text_from_binary_ppt(path: str) -> str:
    """Fallback parser for legacy binary .ppt files (OLE2 format)."""
    text_chunks = []
    try:
        import olefile
        if olefile.isOleFile(path):
            with olefile.OleFileIO(path) as ole:
                if ole.exists('PowerPoint Document'):
                    stream = ole.openstream('PowerPoint Document').read()
                    import re
                    # Extract printable UTF-16LE strings (standard PPT text streams)
                    utf16_matches = re.findall(b'(?:[\x20-\x7e]\x00){3,}', stream)
                    for m in utf16_matches:
                        try:
                            decoded = m.decode('utf-16le', errors='ignore').strip()
                            if len(decoded) > 3 and not decoded.startswith('PowerPoint'):
                                text_chunks.append(decoded)
                        except Exception:
                            pass
                    # Extract ASCII strings
                    ascii_matches = re.findall(b'[\x20-\x7e]{4,}', stream)
                    for m in ascii_matches:
                        try:
                            decoded = m.decode('ascii', errors='ignore').strip()
                            if len(decoded) > 3 and not any(k in decoded for k in ['PowerPoint', 'Current User', 'Document Summary']):
                                text_chunks.append(decoded)
                        except Exception:
                            pass
    except Exception as ole_err:
        logger.warning(f"Olefile extraction notice for {path}: {ole_err}")

    # Fallback to direct raw binary regex string extraction
    if not text_chunks:
        try:
            with open(path, "rb") as f:
                content = f.read()
            import re
            utf16_matches = re.findall(b'(?:[\x20-\x7e]\x00){4,}', content)
            for m in utf16_matches:
                try:
                    decoded = m.decode('utf-16le', errors='ignore').strip()
                    if len(decoded) > 3:
                        text_chunks.append(decoded)
                except Exception:
                    pass
        except Exception as raw_err:
            logger.warning(f"Raw binary extraction failed for {path}: {raw_err}")

    # Deduplicate while preserving order
    seen = set()
    unique_chunks = []
    for c in text_chunks:
        if c not in seen:
            seen.add(c)
            unique_chunks.append(c)

    return "\n".join(unique_chunks)


def parse_pptx(path: str) -> List[Dict[str, Any]]:
    """python-pptx slide-by-slide text extraction with legacy binary .ppt fallback."""
    from pptx import Presentation
    logger.info(f"Parsing PPT/PPTX: {path}")
    source = os.path.basename(path)

    # Strategy 1: OpenXML (.pptx) via python-pptx
    try:
        prs = Presentation(path)
        pages = []
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
        if pages:
            return pages
    except Exception as exc:
        logger.warning(f"python-pptx could not parse {path} as OpenXML: {exc}. Attempting legacy .ppt fallback...")

    # Strategy 2: Legacy binary .ppt format fallback
    full_text = _extract_text_from_binary_ppt(path)
    if not full_text.strip():
        logger.warning(f"No text extracted from PPT file {source}")
        return []

    # Break into pseudo-pages (~2000 chars per page)
    page_size = 2000
    pages = []
    chunks = [full_text[i:i + page_size] for i in range(0, len(full_text), page_size)]
    for i, c in enumerate(chunks, start=1):
        if c.strip():
            pages.append({"text": c.strip(), "page": i, "source": source})
    return pages


_whisper_model_cache = None
_whisper_model_lock = threading.Lock()


def _get_whisper_model():
    """Lazy thread-safe singleton for Faster-Whisper model with CPU fallback handling."""
    global _whisper_model_cache
    if _whisper_model_cache is not None:
        return _whisper_model_cache

    with _whisper_model_lock:
        if _whisper_model_cache is not None:
            return _whisper_model_cache

        from faster_whisper import WhisperModel
        from app.config import get_settings
        settings = get_settings()

        logger.info(f"[WHISPER] Loading Whisper model ('{settings.whisper_model}') on {settings.whisper_device}...")

        # Temporarily override HF_HUB_OFFLINE so initial model download succeeds on first run
        old_offline = os.environ.pop("HF_HUB_OFFLINE", None)

        model = None
        try:
            for comp_type in ["int8", "default", "float32"]:
                try:
                    logger.info(f"[WHISPER] Attempting load with compute_type='{comp_type}'...")
                    model = WhisperModel(settings.whisper_model, device=settings.whisper_device, compute_type=comp_type)
                    logger.info(f"[WHISPER] Successfully loaded Whisper model with compute_type='{comp_type}'")
                    break
                except Exception as exc:
                    logger.warning(f"[WHISPER] Failed with compute_type='{comp_type}': {exc}")
        finally:
            if old_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = old_offline

        if model is None:
            raise RuntimeError(f"Could not initialize Faster-Whisper model '{settings.whisper_model}'.")

        _whisper_model_cache = model
        return _whisper_model_cache


def _extract_audio_to_wav(media_path: str) -> tuple[str, bool]:
    """
    Extract/normalize any audio or video file into a standard 16kHz mono 16-bit PCM WAV file.
    Returns tuple of (wav_path, is_temp_file).
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    extracted = False

    # Strategy 1: ffmpeg CLI (Fastest & most reliable)
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", media_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path],
            check=True, capture_output=True
        )
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
            extracted = True
    except Exception as ffmpeg_err:
        logger.warning(f"[AUDIO] ffmpeg CLI execution failed for {media_path}: {ffmpeg_err}")

    # Strategy 2: PyAV fallback (pure Python bindings)
    if not extracted:
        try:
            import av
            container = av.open(media_path)
            audio_stream = next((s for s in container.streams if s.type == 'audio'), None)
            if audio_stream:
                output_container = av.open(wav_path, 'w', format='wav')
                out_stream = output_container.add_stream('pcm_s16le', rate=16000)
                out_stream.channels = 1

                resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
                for frame in container.decode(audio_stream):
                    for resampled_frame in resampler.resample(frame):
                        for packet in out_stream.encode(resampled_frame):
                            output_container.mux(packet)
                for packet in out_stream.encode(None):
                    output_container.mux(packet)
                output_container.close()
                container.close()
                if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                    extracted = True
        except Exception as av_err:
            logger.warning(f"[AUDIO] PyAV audio extraction failed for {media_path}: {av_err}")

    if extracted:
        return wav_path, True
    else:
        if os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass
        return media_path, False


def _transcribe_with_whisper(audio_path: str, source: str) -> List[Dict[str, Any]]:
    """Faster-Whisper transcription. Returns segments grouped into ~30-second pseudo-pages."""
    logger.info(f"[WHISPER] Transcribing audio from {source}...")
    try:
        model = _get_whisper_model()
        
        try:
            segments, info = model.transcribe(audio_path, beam_size=5, vad_filter=True)
            segment_list = list(segments)
        except Exception as vad_err:
            logger.warning(f"[WHISPER] Transcribe with vad_filter=True failed for {source} ({vad_err}); retrying with vad_filter=False...")
            segments, info = model.transcribe(audio_path, beam_size=5, vad_filter=False)
            segment_list = list(segments)

        pages = []
        current_text = []
        current_page = 1
        page_duration = 30.0
        start_time = 0.0

        for segment in segment_list:
            text = segment.text.strip()
            if text:
                current_text.append(text)
            if segment.end - start_time >= page_duration:
                joined = " ".join(current_text).strip()
                if joined:
                    pages.append({
                        "text": joined,
                        "page": current_page,
                        "source": source
                    })
                    current_page += 1
                current_text = []
                start_time = segment.end

        if current_text:
            joined = " ".join(current_text).strip()
            if joined:
                pages.append({
                    "text": joined,
                    "page": current_page,
                    "source": source
                })

        logger.info(f"[WHISPER] Transcribed {source}: extracted {len(pages)} pages/chunks from {len(segment_list)} segments")
        return pages
    except Exception as exc:
        logger.exception(f"[WHISPER] Transcription failed for {source}: {exc}")
        return []


def parse_audio(path: str) -> List[Dict[str, Any]]:
    """Extract audio and transcribe with Whisper."""
    source = os.path.basename(path)
    logger.info(f"[AUDIO] Processing audio file: {path}")
    wav_path, is_temp = _extract_audio_to_wav(path)
    try:
        return _transcribe_with_whisper(wav_path, source)
    finally:
        if is_temp and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass


def parse_image(path: str) -> List[Dict[str, Any]]:
    """Extract text from standalone images (PNG, JPG, WEBP, BMP, TIFF) using Tesseract OCR."""
    try:
        from PIL import Image, ImageEnhance
        import pytesseract
    except ImportError:
        logger.error("[IMAGE] pytesseract or PIL is not installed; cannot perform image OCR.")
        return []

    source = os.path.basename(path)
    logger.info(f"[IMAGE] Parsing image with OCR: {path}")

    try:
        image = Image.open(path)
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")

        # Contrast enhancement for crisp text OCR
        enhancer = ImageEnhance.Contrast(image)
        enhanced_image = enhancer.enhance(1.4)

        text = pytesseract.image_to_string(enhanced_image, lang="eng", config="--psm 3").strip()
        if not text:
            # Fallback with raw image and PSM 6 (single uniform block of text)
            text = pytesseract.image_to_string(image, lang="eng", config="--psm 6").strip()

        if not text:
            logger.warning(f"[IMAGE] No legible text extracted from {source}")
            return []

        logger.info(f"[IMAGE] Successfully extracted {len(text)} chars from {source}")
        return [{"text": text, "page": 1, "source": source}]
    except Exception as exc:
        logger.exception(f"[IMAGE] Failed to OCR image {source}: {exc}")
        return []


def parse_video(path: str) -> List[Dict[str, Any]]:
    """Extract audio from video file and transcribe with Whisper."""
    source = os.path.basename(path)
    logger.info(f"[VIDEO] Processing video file: {path}")
    wav_path, is_temp = _extract_audio_to_wav(path)
    try:
        return _transcribe_with_whisper(wav_path, source)
    finally:
        if is_temp and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass

