"""Extracción local de texto de adjuntos (camino B): pypdf para PDF, python-docx para Word.

Cada texto extraído se recorta a ``MAX_ATTACHMENT_CHARS`` para proteger el
presupuesto del prompt; el chunking de verdad llega con RAG en el módulo 3.
"""

from io import BytesIO

import structlog
from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader

from app.config import settings

log = structlog.get_logger()

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB por archivo


class UnsupportedAttachment(Exception):
    pass


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


async def extract_text(file: UploadFile, max_chars: int = settings.MAX_ATTACHMENT_CHARS) -> str:
    data = await file.read()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise UnsupportedAttachment(f"{file.filename}: supera {MAX_ATTACHMENT_BYTES // 1024 // 1024} MB")

    name = (file.filename or "").lower()
    try:
        if name.endswith(".pdf"):
            text = _extract_pdf(data)
        elif name.endswith(".docx"):
            text = _extract_docx(data)
        else:
            raise UnsupportedAttachment(f"{file.filename}: solo se admiten .pdf y .docx")
    except UnsupportedAttachment:
        raise
    except Exception as e:
        raise UnsupportedAttachment(f"{file.filename}: error al procesar el archivo ({e})") from e

    text = text.strip()
    if not text:
        raise UnsupportedAttachment(f"{file.filename}: el archivo está vacío después de procesarlo")

    if len(text) > max_chars:
        log.info("attachment_truncated", filename=file.filename, original_chars=len(text), kept_chars=max_chars)
        text = text[:max_chars]
    return text


async def build_transcript(transcript: str, attachments: list[UploadFile]) -> str:
    """Concatena el transcript con el texto de cada adjunto, entre marcadores de inicio y fin."""
    parts = [transcript]
    for file in attachments:
        text = await extract_text(file)
        parts.append(f"--- attachment: {file.filename} ---\n{text}\n--- end attachment ---")
    return "\n\n".join(parts)
