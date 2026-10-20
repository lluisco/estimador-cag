"""Parser de transcripciones .txt.

El corpus mezcla dos formatos; el parser detecta cuál es y cambia la granularidad:

* **Con etiquetas** ``[hh:mm:ss] Speaker: texto``: un ``Document`` por turno, con
  ``speaker`` y ``timestamp`` en ``metadata.extra`` para poder filtrar después.
* **Sin etiquetas** (legacy, anterior a 2024): un ``Document`` por bloque (separado
  por líneas en blanco), sin ``speaker``. Mejor admitir que no sé quién habla
  que inventármelo.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import ClassVar

from app.ingestion.documents.models import Document, DocumentMetadata
from app.ingestion.loaders.filesystem import LoadedBlob
from app.ingestion.parsers.protocol import ParseContext

# [10:00:12] Laura Fernández: …
_TURN_RE = re.compile(r"^\[(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]\s*(?P<speaker>[^:]+?):\s*(?P<text>.*)$")
# Con menos turnos etiquetados que esto, el fichero se trata como legacy.
_MIN_TAGGED_TURNS = 3


class TranscriptTxtParser:
    supported_formats: ClassVar[set[str]] = {"txt"}

    def parse(self, blob: LoadedBlob, context: ParseContext) -> Iterable[Document]:
        text = blob.bytes_.decode("utf-8", errors="replace")
        if _has_speaker_tags(text):
            yield from self._parse_tagged(text, blob, context)
        else:
            yield from self._parse_legacy(text, blob, context)

    def _parse_tagged(self, text: str, blob: LoadedBlob, context: ParseContext) -> Iterable[Document]:
        for idx, line in enumerate(text.splitlines()):
            m = _TURN_RE.match(line.strip())
            if not m or not m.group("text").strip():
                continue
            yield Document(
                id=f"{context.source.name}:{blob.relative_path}:turn-{idx:04d}",
                text=m.group("text").strip(),
                metadata=_meta(
                    blob,
                    context,
                    extra={
                        "speaker": m.group("speaker").strip(),
                        "timestamp": m.group("ts").strip(),
                        "format_mode": "tagged",
                    },
                ),
            )

    def _parse_legacy(self, text: str, blob: LoadedBlob, context: ParseContext) -> Iterable[Document]:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        for idx, block in enumerate(blocks):
            yield Document(
                id=f"{context.source.name}:{blob.relative_path}:block-{idx:04d}",
                text=block,
                metadata=_meta(blob, context, extra={"format_mode": "legacy", "block_index": idx}),
            )


def _has_speaker_tags(text: str) -> bool:
    matches = sum(1 for line in text.splitlines() if _TURN_RE.match(line.strip()))
    return matches >= _MIN_TAGGED_TURNS


def _meta(blob: LoadedBlob, context: ParseContext, extra: dict) -> DocumentMetadata:
    return DocumentMetadata(
        source_name=context.source.name,
        source_version=context.source_version,
        ingested_at=context.ingested_at,
        lineage=list(context.source.lineage),
        sensitivity_pii_flags=list(context.source.sensitivity.pii_flags),
        sensitivity_access_level=context.source.sensitivity.access_level,
        location=blob.relative_path,
        extra=extra,
    )
