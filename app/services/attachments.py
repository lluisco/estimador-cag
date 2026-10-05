from io import BytesIO

from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB por archivo


class UnsupportedAttachment(Exception):
    pass


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


async def extract_text(file: UploadFile) -> str:
    data = await file.read()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise UnsupportedAttachment(f"{file.filename}: supera {MAX_ATTACHMENT_BYTES // 1024 // 1024} MB")

    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        text = _extract_pdf(data)
    elif name.endswith(".docx"):
        text = _extract_docx(data)
    else:
        raise UnsupportedAttachment(f"{file.filename}: solo se admiten .pdf y .docx")
    return text.strip()


async def build_transcript(transcript: str, attachments: list[UploadFile]) -> str:
    """Concatena el transcript con el texto de cada adjunto, separados por un marcador claro."""
    parts = [transcript]
    for file in attachments:
        parts.append(f"--- attachment: {file.filename} ---\n{await extract_text(file)}")
    return "\n\n".join(parts)
