"""Parser del esquema JSON de presupuestos del Proyecto 2.

Decisión clave: cada presupuesto se renderiza a markdown estructurado, no a
``json.dumps``. El embedder trabaja con prosa: "¿quién es el cliente?" se parece
más a ``## Cliente - Nombre: Acme`` que a ``{"client_name":"Acme"}``. Los números
se quedan; solo cambia el marco. Es una decisión de retrieval adelantada al parser.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import ClassVar

from app.ingestion.documents.models import Document, DocumentMetadata
from app.ingestion.loaders.filesystem import LoadedBlob
from app.ingestion.parsers.protocol import ParseContext


class BudgetJsonParser:
    supported_formats: ClassVar[set[str]] = {"json"}

    def parse(self, blob: LoadedBlob, context: ParseContext) -> Iterable[Document]:
        payload = json.loads(blob.bytes_)
        yield Document(
            id=f"{context.source.name}:{payload['budget_id']}:{blob.relative_path}",
            text=_render_budget_markdown(payload),
            metadata=DocumentMetadata(
                source_name=context.source.name,
                source_version=context.source_version,
                ingested_at=context.ingested_at,
                lineage=list(context.source.lineage),
                sensitivity_pii_flags=list(context.source.sensitivity.pii_flags),
                sensitivity_access_level=context.source.sensitivity.access_level,
                location=blob.relative_path,
                extra={
                    key: payload.get(key)
                    for key in ("budget_id", "client_code", "currency", "total_amount", "signed_at")
                },
            ),
        )


def _render_budget_markdown(payload: dict) -> str:
    """Un H1 (el id del presupuesto) y un H2 por bloque semántico."""
    currency = payload.get("currency", "?")
    lines = [
        f"# Presupuesto {payload.get('budget_id', '?')}",
        "",
        "## Cliente",
        f"- Nombre: {payload.get('client_name', '-')}",
        f"- Código interno: {payload.get('client_code', '-')}",
    ]
    if payload.get("contact"):
        lines.append(f"- Contacto: {payload['contact']}")
    if payload.get("contact_email"):
        lines.append(f"- Email: {payload['contact_email']}")
    lines += [
        "",
        "## Total",
        f"- Importe: {payload.get('total_amount', '?')} {currency}",
        f"- Firmado: {payload.get('signed_at', '-')}",
        "",
        "## Fases",
    ]
    phases = payload.get("phases") or []
    if not phases:
        lines.append("- (sin fases declaradas)")
    for phase in phases:
        lines.append(
            f"- **{phase.get('name', '?')}** — {phase.get('weeks', '?')} semanas · "
            f"{phase.get('amount', '?')} {currency}"
        )
    lines.append("")
    if payload.get("notes"):
        lines += ["## Notas", payload["notes"], ""]
    return "\n".join(lines).rstrip() + "\n"
