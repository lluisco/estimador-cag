import uuid
from dataclasses import dataclass

import pytest

from app.ingestion.pii import ConsistentPseudonymizer, InMemoryMappingStore


@dataclass
class _Hit:
    entity_type: str
    start: int
    end: int
    score: float = 0.9


class _StubAnalyzer:
    def __init__(self, hits: list[_Hit]) -> None:
        self._hits = hits

    def analyze(self, *, text, language, entities=None):
        return list(self._hits)


def _pseudo(hits, store=None, salt="sal-test"):
    return ConsistentPseudonymizer(
        analyzer=_StubAnalyzer(hits),
        mapping_store=store or InMemoryMappingStore(),
        salt=salt,
    )


def _span(text: str, needle: str, entity: str, score: float = 0.9) -> _Hit:
    start = text.index(needle)
    return _Hit(entity, start, start + len(needle), score)


def test_el_pseudonimo_no_depende_del_orden_ni_de_la_store():
    # Dos procesos con la store vacía deben dar el mismo pseudónimo al mismo valor:
    # si dependiera de una secuencia global, tras un reinicio se reasignarían nombres.
    text = "Habló Laura Fernández con Javier Romero."
    hits = [_span(text, "Laura Fernández", "PERSON"), _span(text, "Javier Romero", "PERSON")]
    primero = _pseudo(hits).pseudonymize(text).pseudonymized_text
    segundo = _pseudo(list(reversed(hits))).pseudonymize(text).pseudonymized_text
    assert primero == segundo


def test_la_sal_cambia_los_pseudonimos():
    text = "Habló Laura Fernández."
    hits = [_span(text, "Laura Fernández", "PERSON")]
    a = _pseudo(hits, salt="sal-a").pseudonymize(text).pseudonymized_text
    b = _pseudo(hits, salt="sal-b").pseudonymize(text).pseudonymized_text
    assert a != b


def test_solape_gana_el_score_mas_alto():
    # El falso positivo de la clase: un código de cliente detectado también como persona.
    text = "Cliente CLI-0078 confirmó."
    hits = [_span(text, "CLI-0078", "CLIENT_CODE", 0.95), _span(text, "CLI-0078", "PERSON", 0.5)]
    result = _pseudo(hits).pseudonymize(text)
    assert [m.entity_type for m in result.applied] == ["CLIENT_CODE"]
    assert result.pseudonymized_text.startswith("Cliente CLI-")
    assert "CLI-0078" not in result.pseudonymized_text


def test_solape_parcial_no_corrompe_el_texto():
    text = "Hable con Ana Pérez López hoy."
    hits = [_span(text, "Ana Pérez", "PERSON", 0.6), _span(text, "Pérez López", "PERSON", 0.8)]
    result = _pseudo(hits).pseudonymize(text)
    assert len(result.applied) == 1
    assert result.pseudonymized_text.startswith("Hable con Ana ")  # solo se sustituyó "Pérez López"
    assert result.pseudonymized_text.endswith(" hoy.")


def test_olvidar_hace_que_el_valor_reciba_un_pseudonimo_nuevo_en_la_store():
    text = "Habló Laura Fernández."
    store = InMemoryMappingStore()
    pseudo = _pseudo([_span(text, "Laura Fernández", "PERSON")], store)
    applied = pseudo.pseudonymize(text).applied[0]

    assert store.forget(applied.entity_type, applied.original_hash) is True
    assert store.forget(applied.entity_type, applied.original_hash) is False


def test_la_store_no_recibe_el_valor_en_claro():
    text = "Habló Laura Fernández."
    store = InMemoryMappingStore()
    _pseudo([_span(text, "Laura Fernández", "PERSON")], store).pseudonymize(text)
    assert all("Laura" not in h for _, h in store._mappings)


@pytest.fixture
def pg_session():
    try:
        from sqlalchemy import text

        from app.persistence.database import SessionLocal

        session = SessionLocal()
        session.execute(text("select 1 from pseudonym_mappings limit 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("Postgres con la migración aplicada no disponible")
    yield session
    session.close()


def test_postgres_lookup_or_create_es_idempotente_y_forget_borra(pg_session):
    from app.ingestion.pii import PostgresMappingStore

    store = PostgresMappingStore(pg_session)
    entity, digest = "TEST_ENTITY", uuid.uuid4().hex
    try:
        first = store.lookup_or_create(entity, digest, lambda: "uno")
        again = store.lookup_or_create(entity, digest, lambda: "dos")
        assert first == again == "uno"
    finally:
        assert store.forget(entity, digest) is True
    assert store.forget(entity, digest) is False
