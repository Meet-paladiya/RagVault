from typing import List, Dict, Any
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

SUPPORTED_EXTENSIONS = (
    {".pdf", ".pptx", ".ppt"}
    | AUDIO_EXTENSIONS
    | VIDEO_EXTENSIONS
    | TEXT_EXTENSIONS
    | IMAGE_EXTENSIONS
    | {".docx", ".doc"}
)

def parse_file(path: str) -> List[Dict[str, Any]]:
    """Dispatch to the right parser based on extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext in {".pptx", ".ppt"}:
        return parse_pptx(path)
    elif ext in AUDIO_EXTENSIONS:
        return parse_audio(path)
    elif ext in VIDEO_EXTENSIONS:
        return parse_video(path)
    elif ext in TEXT_EXTENSIONS:
        return parse_text(path)
    elif ext in {".docx", ".doc"}:
        return parse_docx(path)
    elif ext in IMAGE_EXTENSIONS:
        return parse_image(path)
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

    # Fallback for legacy binary .doc files (OLE2 format)
    if not full_text.strip() and path.lower().endswith(".doc"):
        try:
            with open(path, "rb") as f:
                content = f.read()
            u_chunks = re.findall(b'(?:[\x20-\x7e]\x00){4,}', content)
            utf16_text = [m.decode('utf-16le', errors='ignore').strip() for m in u_chunks]
            a_chunks = re.findall(b'[\x20-\x7e]{4,}', content)
            ascii_text = [m.decode('ascii', errors='ignore').strip() for m in a_chunks if not any(k in m.decode('ascii', errors='ignore') for k in ['WordDocument', 'Current User', 'CompObj'])]
            full_text = " ".join([t for t in utf16_text + ascii_text if len(t) > 4])
        except Exception as doc_err:
            logger.warning(f"Legacy .doc extraction notice for {path}: {doc_err}")

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
    Hybrid PDF extraction:
    - PyMuPDF extracts selectable text.
    - PaddleOCR reads scanned pages.
    - PaddleOCR also reads text inside embedded images
      on mixed-content pages.
    - Page number and source metadata are preserved.
    """
    import fitz
    import numpy as np

    logger.info("[PDF] Parsing PDF: %s", path)

    pages = []
    source = os.path.basename(path)

    # Create PaddleOCR only when OCR is actually needed.
    ocr_engine = None

    def get_ocr_engine():
        nonlocal ocr_engine

        if ocr_engine is None:
            from paddleocr import PaddleOCR

            ocr_engine = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

        return ocr_engine

    def run_ocr(image: np.ndarray) -> str:
        """Run local PaddleOCR on an RGB image."""
        try:
            results = get_ocr_engine().predict(image)
            lines = []

            for result in results:
                recognized = result.get("rec_texts", [])
                scores = result.get("rec_scores", [])

                for index, line in enumerate(recognized):
                    line = str(line).strip()

                    # Ignore very low-confidence results.
                    if not line:
                        continue

                    if index < len(scores) and float(scores[index]) < 0.50:
                        continue

                    lines.append(line)

            return "\n".join(lines).strip()

        except Exception:
            logger.exception("[OCR] PaddleOCR failed")
            return ""

    def render_region(page, rect=None) -> np.ndarray:
        """Render a page or a selected image region."""
        pix = page.get_pixmap(
            dpi=250,
            clip=rect,
            alpha=False,
        )

        image = np.frombuffer(
            pix.samples,
            dtype=np.uint8,
        ).reshape(pix.height, pix.width, pix.n)

        # PaddleOCR expects an RGB image.
        if pix.n == 4:
            image = image[:, :, :3]

        return image.copy()

    def normalize(text: str) -> str:
        return " ".join(text.lower().split())

    try:
        with fitz.open(path) as doc:
            for index, page in enumerate(doc):
                page_number = index + 1

                # 1. Extract normal, selectable PDF text.
                digital_text = page.get_text("text").strip()
                combined_text = digital_text

                page_area = max(
                    float(page.rect.width * page.rect.height),
                    1.0,
                )

                # 2. Inspect embedded image locations.
                try:
                    image_infos = page.get_image_info()
                except Exception:
                    logger.exception(
                        "[PDF] Could not inspect images on page %d",
                        page_number,
                    )
                    image_infos = []

                image_regions = []

                for info in image_infos:
                    bbox = info.get("bbox")

                    if not bbox:
                        continue

                    rect = fitz.Rect(bbox) & page.rect

                    if rect.is_empty:
                        continue

                    coverage = (
                        rect.width * rect.height
                    ) / page_area

                    # Very tiny images/icons usually do not contain
                    # useful text. Adjust this threshold if needed.
                    if coverage < 0.003:
                        continue

                    image_regions.append((rect, coverage))

                large_page_image = any(
                    coverage >= 0.50
                    for _, coverage in image_regions
                )

                # 3. Scanned page: use OCR over the whole page whenever digital text is absent.
                if not digital_text:
                    logger.info(
                        "[OCR] Scanned page %d (no digital text); running full-page OCR",
                        page_number,
                    )

                    combined_text = run_ocr(
                        render_region(page)
                    )

                # 4. Mixed page: preserve digital text and OCR
                # individual embedded images, not the whole page.
                elif image_regions:
                    for image_index, (rect, coverage) in enumerate(
                        image_regions,
                        start=1,
                    ):
                        # Do not OCR a full-page image if a digital
                        # text layer already exists. It could duplicate
                        # almost the entire page.
                        if digital_text and coverage >= 0.50:
                            continue

                        logger.debug(
                            "[OCR] Page %d, image %d: OCR region",
                            page_number,
                            image_index,
                        )

                        image_text = run_ocr(
                            render_region(page, rect)
                        )

                        if not image_text:
                            continue

                        # 5. Avoid appending OCR text already present
                        # in the digital text or earlier OCR output.
                        existing = normalize(combined_text)
                        new_lines = []

                        for line in image_text.splitlines():
                            line = line.strip()

                            if not line:
                                continue

                            normalized_line = normalize(line)

                            if normalized_line not in existing:
                                new_lines.append(line)
                                existing += " " + normalized_line

                        if new_lines:
                            combined_text = (
                                combined_text + "\n\n"
                                if combined_text else ""
                            ) + "\n".join(new_lines)

                # 6. Keep the same output format used by your pipeline.
                if combined_text.strip():
                    pages.append({
                        "text": combined_text.strip(),
                        "page": page_number,
                        "source": source,
                    })

                    logger.info(
                        "[PDF] Page %d extracted: %d characters",
                        page_number,
                        len(combined_text),
                    )
                else:
                    logger.warning(
                        "[PDF] Page %d produced no text",
                        page_number,
                    )

    except Exception:
        logger.exception("[PDF] Failed to parse %s", path)
        raise

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
            utf16_matches = re.findall(b'(?:[\x20-\x7e]\x00){4,}', content)
            for m in utf16_matches:
                try:
                    decoded = m.decode('utf-16le', errors='ignore').strip()
                    if len(decoded) > 3:
                        text_chunks.append(decoded)
                except Exception:
                    pass
            ascii_matches = re.findall(b'[\x20-\x7e]{4,}', content)
            for m in ascii_matches:
                try:
                    decoded = m.decode('ascii', errors='ignore').strip()
                    if len(decoded) > 3 and not any(k in decoded for k in ['PowerPoint', 'Current User', 'Document Summary']):
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


def _extract_text_from_pptx_shape(shape) -> List[str]:
    """Recursively extract readable text from any PowerPoint shape (text frames, tables, groups)."""
    texts: List[str] = []
    try:
        # 1. Text frame (titles, text boxes, autoshapes, placeholders)
        if getattr(shape, "has_text_frame", False) and shape.text_frame:
            for paragraph in shape.text_frame.paragraphs:
                p_text = "".join(run.text for run in paragraph.runs).strip() or paragraph.text.strip()
                if p_text:
                    texts.append(p_text)

        # 2. Tables
        elif getattr(shape, "has_table", False) and shape.table:
            for row in shape.table.rows:
                row_vals = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                if row_vals:
                    texts.append(" | ".join(row_vals))

        # 3. Group shapes (nested shapes inside a group)
        elif getattr(shape, "shapes", None) is not None:
            for sub_shape in shape.shapes:
                texts.extend(_extract_text_from_pptx_shape(sub_shape))

        # 4. Fallback for any other shape having a .text attribute
        elif hasattr(shape, "text") and shape.text:
            t = shape.text.strip()
            if t:
                texts.append(t)
    except Exception as e:
        logger.debug(f"Error extracting PPTX shape text: {e}")

    return texts


def parse_pptx(path: str) -> List[Dict[str, Any]]:
    """python-pptx slide-by-slide text extraction with legacy binary .ppt fallback."""
    try:
        from pptx import Presentation
    except ImportError:
        logger.warning("python-pptx library is not installed in current Python environment. Attempting legacy fallback.")
        Presentation = None

    logger.info(f"Parsing PPT/PPTX: {path}")
    source = os.path.basename(path)

    # Strategy 1: OpenXML (.pptx) via python-pptx
    if Presentation is not None:
        try:
            prs = Presentation(path)
            pages = []
            for i, slide in enumerate(prs.slides):
                text: List[str] = []
                for shape in slide.shapes:
                    text.extend(_extract_text_from_pptx_shape(shape))

                # Also extract slide presenter notes if available
                try:
                    if getattr(slide, "has_notes_slide", False) and slide.notes_slide:
                        notes_frame = getattr(slide.notes_slide, "notes_text_frame", None)
                        if notes_frame and notes_frame.text and notes_frame.text.strip():
                            text.append(f"Notes: {notes_frame.text.strip()}")
                except Exception:
                    pass

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

        # Check local offline model candidates first
        local_candidates = [
            os.path.join(os.environ.get("MODEL_DIR", "/models"), f"whisper-{settings.whisper_model}"),
            os.path.join(os.environ.get("MODEL_DIR", "/models"), "whisper"),
            os.path.join(settings.hf_home, "whisper", f"whisper-{settings.whisper_model}"),
            os.path.join(settings.hf_home, "whisper"),
        ]
        model_target = settings.whisper_model
        for cand in local_candidates:
            if os.path.exists(cand) and os.path.exists(os.path.join(cand, "model.bin")):
                logger.info(f"[WHISPER] Found local offline Whisper model at: {cand}")
                model_target = cand
                break

        whisper_dir = os.path.join(settings.hf_home, "whisper") if hasattr(settings, "hf_home") else None
        if whisper_dir:
            os.makedirs(whisper_dir, exist_ok=True)

        logger.info(f"[WHISPER] Loading Whisper model ('{model_target}') on {settings.whisper_device}...")

        # Temporarily override HF_HUB_OFFLINE so initial model download succeeds on first run
        old_offline = os.environ.pop("HF_HUB_OFFLINE", None)

        model = None
        try:
            for comp_type in ["int8", "default", "float32"]:
                for dl_root in ([whisper_dir, None] if whisper_dir else [None]):
                    try:
                        logger.info(f"[WHISPER] Attempting load with compute_type='{comp_type}', download_root={dl_root}...")
                        model = WhisperModel(
                            model_target,
                            device=settings.whisper_device,
                            compute_type=comp_type,
                            download_root=dl_root,
                            cpu_threads=4,
                        )
                        logger.info(f"[WHISPER] Successfully loaded Whisper model with compute_type='{comp_type}'")
                        break
                    except Exception as exc:
                        logger.warning(f"[WHISPER] Failed with compute_type='{comp_type}', download_root={dl_root}: {exc}")
                if model is not None:
                    break
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

    # If it is already a WAV file, use it directly
    if media_path.lower().endswith(".wav"):
        return media_path, False

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

    if extracted:
        return wav_path, True

    # Clean up empty temp file if ffmpeg failed
    if os.path.exists(wav_path):
        try:
            os.unlink(wav_path)
        except Exception:
            pass

    # Strategy 2: Faster-Whisper natively decodes audio/video files via its built-in PyAV reader
    return media_path, False


def _transcribe_with_whisper(audio_path: str, source: str) -> List[Dict[str, Any]]:
    """Faster-Whisper transcription. Returns segments grouped into ~30-second pseudo-pages."""
    logger.info(f"[WHISPER] Transcribing audio from {source}...")
    try:
        model = _get_whisper_model()
        
        # beam_size=1 provides 3x-5x faster CPU transcription with virtually identical accuracy
        try:
            segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=True)
            segment_list = list(segments)
            if not segment_list:
                logger.info(f"[WHISPER] vad_filter=True produced 0 segments for {source}; retrying with vad_filter=False...")
                segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=False)
                segment_list = list(segments)
        except Exception as vad_err:
            logger.warning(f"[WHISPER] Transcribe with vad_filter=True failed for {source} ({vad_err}); retrying with vad_filter=False...")
            segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=False)
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
        raise RuntimeError(f"Whisper transcription failed for {source}: {exc}")


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

