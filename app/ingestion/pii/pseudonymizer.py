"""Pseudonimizador consistente: mismo valor → mismo pseudónimo, siempre.

Flujo:

1. Presidio analiza el texto y devuelve las entidades con sus posiciones.
2. Se descartan los solapes: gana el score más alto (un regex específico de 0,95
   gana a un NER genérico de 0,4-0,6).
3. Por cada entidad se calcula un HMAC-SHA256 del valor con la sal del servidor.
   La mapping store usa ese hash como clave; el valor en claro no sale de aquí.
4. ``lookup_or_create`` devuelve un pseudónimo estable, generado con el Faker del
   tipo de entidad la primera vez que se ve ese hash.
5. Se sustituye de derecha a izquierda para que los offsets previos no se desplacen.

Pseudonimizar y no anonimizar es una decisión de RAG: ``<PERSON>`` genérico tira la
similitud entre un 15 y un 25 % según las pruebas internas del curso, mientras que
un nombre verosímil y consistente conserva la estructura semántica.

La reversibilidad vive en la store, no aquí: borrar una fila por
``(entity_type, original_hash)`` invalida las consultas futuras de ese valor sin
tocar el corpus.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from faker import Faker
from presidio_analyzer import AnalyzerEngine

from app.ingestion.pii.mapping_store import MappingStore


@dataclass(frozen=True)
class AppliedMapping:
    """Una entidad sustituida en el texto de entrada."""

    entity_type: str
    original_hash: str
    pseudonym: str
    start: int
    end: int


@dataclass(frozen=True)
class PseudonymizationResult:
    pseudonymized_text: str
    applied: list[AppliedMapping]


class ConsistentPseudonymizer:
    def __init__(
        self,
        *,
        analyzer: AnalyzerEngine,
        mapping_store: MappingStore,
        salt: str,
        faker_locale: str = "es_ES",
        language: str = "es",
    ) -> None:
        self._analyzer = analyzer
        self._store = mapping_store
        self._salt = salt.encode("utf-8")
        self._language = language
        self._faker = Faker(faker_locale)

    def pseudonymize(self, text: str, *, entities: list[str] | None = None) -> PseudonymizationResult:
        results = self._analyzer.analyze(text=text, language=self._language, entities=entities)
        results = _drop_overlaps(results)
        if not results:
            return PseudonymizationResult(pseudonymized_text=text, applied=[])

        out = text
        applied: list[AppliedMapping] = []
        # De derecha a izquierda: sustituir no desplaza los offsets de lo que queda a la izquierda.
        for r in sorted(results, key=lambda r: r.end, reverse=True):
            original_hash = self._hash(text[r.start : r.end])
            pseudonym = self._store.lookup_or_create(
                entity_type=r.entity_type,
                original_hash=original_hash,
                new_pseudonym_factory=lambda r=r, h=original_hash: self._generate(r.entity_type, h),
            )
            out = out[: r.start] + pseudonym + out[r.end :]
            applied.append(AppliedMapping(r.entity_type, original_hash, pseudonym, r.start, r.end))

        return PseudonymizationResult(pseudonymized_text=out, applied=applied)

    def _hash(self, value: str) -> str:
        return hmac.new(self._salt, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _generate(self, entity_type: str, original_hash: str) -> str:
        """Pseudónimo determinista a partir del hash del valor original.

        Sembrar Faker con el hash hace el pseudónimo función del valor y de la sal, no
        del orden de llegada. Con una secuencia global, tras reiniciar el proceso la
        siguiente persona nueva recibiría un nombre ya asignado a otra en la tabla.
        """
        seed = int(original_hash[:16], 16)
        self._faker.seed_instance(seed)
        if entity_type == "PERSON":
            return self._faker.name()
        if entity_type == "EMAIL_ADDRESS":
            return self._faker.ascii_company_email()
        if entity_type == "LOCATION":
            return self._faker.city()
        if entity_type == "BUDGET_ID":
            return f"BUDGET-{2020 + seed % 10}-{(seed // 10) % 10_000:04d}"
        if entity_type == "CLIENT_CODE":
            return f"CLI-{seed % 10_000:04d}"
        return f"REDACTED-{original_hash[:8]}"


def _drop_overlaps(results: list) -> list:
    """Conserva, de cada grupo de spans solapados, el de mayor score (y, a igualdad, el más largo)."""
    kept: list = []
    for r in sorted(results, key=lambda r: (-r.score, -(r.end - r.start), r.start)):
        if all(r.end <= k.start or r.start >= k.end for k in kept):
            kept.append(r)
    return kept
