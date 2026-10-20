from app.ingestion.architecture import (
    CURRENT_MODEL,
    PROYECTO_2,
    CAGViability,
    CorpusProfile,
    assess_cag_viability,
    recommend_architecture,
)


def test_proyecto_2_recomienda_rag():
    # No cabe en la ventana útil y exige trazabilidad + control de acceso.
    assert recommend_architecture(PROYECTO_2, CURRENT_MODEL) == "RAG"


def test_corpus_pequeno_estable_y_sin_restricciones_recomienda_cag():
    corpus = CorpusProfile(
        name="glosario",
        estimated_tokens=20_000,
        refresh_frequency_days=30,
        traceability_required=False,
        access_control_required=False,
    )
    assert recommend_architecture(corpus, CURRENT_MODEL) == "CAG"


def test_cabe_y_es_estable_pero_exige_trazabilidad_recomienda_hibrido():
    corpus = CorpusProfile(
        name="plantillas",
        estimated_tokens=20_000,
        refresh_frequency_days=30,
        traceability_required=True,  # lo único que rompe el CAG puro
        access_control_required=False,
    )
    assert recommend_architecture(corpus, CURRENT_MODEL) == "Hybrid"


def test_viabilidad_cag_es_un_and():
    assert CAGViability(True, True, True, True).viable is True
    assert CAGViability(True, True, True, True).failing_constraints() == []

    una_roja = CAGViability(
        context_window_ok=False,
        cost_ok=True,
        latency_ok=True,
        lost_in_the_middle_ok=True,
    )
    assert una_roja.viable is False
    assert una_roja.failing_constraints() == ["context_window"]


def test_proyecto_2_falla_los_ejes_de_volumen():
    viability = assess_cag_viability(PROYECTO_2, CURRENT_MODEL)
    assert viability.viable is False
    assert "context_window" in viability.failing_constraints()
    assert "lost_in_the_middle" in viability.failing_constraints()
