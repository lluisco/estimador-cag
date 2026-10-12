"""Adjuntos (camino B): el texto extraído llega al LLM, influye en la estimación y no se
arrastra por el historial."""

import asyncio
import io
from types import SimpleNamespace

from docx import Document
from fastapi import UploadFile

from app.services.attachments import extract_text
from tests.conftest import estimate, make_canned_result, new_session

MARKER = "PRESUPUESTO_TOPE"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _fake_pdf_reader(pages: list[str]):
    """Sustituye a ``PdfReader``: el test no depende de generar un PDF binario."""
    return lambda _stream: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in pages]
    )


def _last_user_message(call: dict) -> str:
    return next(m["content"] for m in reversed(call["messages"]) if m["role"] == "user")


def test_docx_attachment_contents_reach_llm(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    docx = _docx_bytes(["Anexo técnico de Nimbus CRM.", "Stack: React + Postgres"])

    response = estimate(
        conversational_client, session_id, "Necesitamos una estimación; ver el anexo adjunto.",
        files=[("attachments", ("spec.docx", docx, DOCX_MIME))],
    )

    assert response.status_code == 200, response.text
    sent = _last_user_message(fake_wrapper.calls_for("EstimationResult")[0])
    assert "--- attachment: spec.docx ---" in sent
    assert "Nimbus CRM" in sent
    assert "--- end attachment ---" in sent


def test_pdf_attachment_changes_the_estimate(conversational_client, fake_wrapper, monkeypatch):
    monkeypatch.setattr("app.services.attachments.PdfReader", _fake_pdf_reader([f"{MARKER}: 36000 EUR"]))
    # el fake sube el coste si el contenido del PDF llega al LLM
    fake_wrapper.estimation_factory = lambda messages: make_canned_result(
        total_cost_eur=36_000 if any(MARKER in m["content"] for m in messages) else 24_000
    )
    session_id = new_session(conversational_client)
    transcript = "Quiero una app de reservas para mi academia"

    without = estimate(conversational_client, session_id, transcript)
    with_pdf = estimate(
        conversational_client, session_id, transcript,
        files=[("attachments", ("spec.pdf", b"%PDF-fake", "application/pdf"))],
    )

    assert without.json()["result"]["total_cost_eur"] == 24_000
    assert with_pdf.json()["result"]["total_cost_eur"] == 36_000


def test_history_keeps_attachment_name_not_its_text(conversational_client, fake_wrapper, monkeypatch):
    monkeypatch.setattr("app.services.attachments.PdfReader", _fake_pdf_reader([f"{MARKER} en el anexo"]))
    session_id = new_session(conversational_client)
    estimate(
        conversational_client, session_id, "Quiero una app de reservas para mi academia",
        files=[("attachments", ("spec.pdf", b"%PDF-fake", "application/pdf"))],
    )

    estimate(conversational_client, session_id, "Una duda más sobre la estimación anterior")

    history = [
        m["content"] for m in fake_wrapper.calls_for("EstimationResult")[1]["messages"][1:-1]
        if m["role"] == "user"
    ]
    assert any("[Adjuntos: spec.pdf]" in text for text in history)
    assert not any(MARKER in text for text in history)


def test_unsupported_attachment_returns_400_and_leaves_session_untouched(conversational_client):
    session_id = new_session(conversational_client)

    response = estimate(
        conversational_client, session_id, "Quiero una app de reservas online",
        files=[("attachments", ("notas.txt", b"hola", "text/plain"))],
    )

    assert response.status_code == 400
    assert conversational_client.get(f"/api/v1/sessions/{session_id}").json()["turns"] == 0


def test_empty_attachment_returns_400(conversational_client):
    session_id = new_session(conversational_client)

    response = estimate(
        conversational_client, session_id, "Quiero una app de reservas online",
        files=[("attachments", ("vacio.docx", _docx_bytes([]), DOCX_MIME))],
    )

    assert response.status_code == 400


def test_attachment_text_is_truncated_to_max_chars():
    upload = UploadFile(filename="largo.docx", file=io.BytesIO(_docx_bytes(["x" * 500])))

    text = asyncio.run(extract_text(upload, max_chars=100))

    assert len(text) == 100
