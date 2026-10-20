import json
from pathlib import Path

from app.ingestion.cleaning import clean_budget_records, validate_with_policy

BUDGETS_DIR = Path("data/seed/budgets")


def _record(**overrides) -> dict:
    base = {
        "budget_id": "BUDGET-2024-0001",
        "client_name": "Acme",
        "client_code": "CLI-0001",
        "currency": "EUR",
        "total_amount": 1000,
        "signed_at": "2024-01-01",
    }
    return base | overrides


def test_seed_corpus_reparte_3_valida_1_cuarentena_1_descartada():
    records = [json.loads(p.read_text("utf-8")) for p in sorted(BUDGETS_DIR.glob("*.json"))]
    df = clean_budget_records(records)
    assert len(df) == 5  # el dedup colapsa BUDGET-2024-0005-v1/v2

    result = validate_with_policy(df)
    assert result.report["valid_rows"] == 3
    assert result.report["quarantined_rows"] == 1
    assert result.report["discarded_rows"] == 1
    assert result.discarded["budget_id"].tolist() == ["BUDGET-2024-0004"]
    # Fecha 12/03/2024 entre ISO: pandas no la repara (NaT) y la validación la detecta.
    assert result.quarantined["budget_id"].tolist() == ["BUDGET-2024-0002"]
    assert result.report["table_level_failures"] == []


def test_importe_entero_limpio_no_falla_el_dtype():
    result = validate_with_policy(clean_budget_records([_record(total_amount=1000)]))
    assert result.report["valid_rows"] == 1
    assert result.report["table_level_failures"] == []


def test_columnas_extra_de_la_limpieza_no_invalidan_filas():
    result = validate_with_policy(clean_budget_records([_record(phases=[], contact="Ana")]))
    assert result.report["valid_rows"] == 1


def test_columna_obligatoria_ausente_queda_registrada_y_no_pasa_en_silencio():
    df = clean_budget_records([_record()]).drop(columns=["currency"])
    result = validate_with_policy(df)
    assert any("currency" in f for f in result.report["table_level_failures"])


def test_importe_negativo_se_descarta_y_nulo_disfrazado_va_a_cuarentena():
    df = clean_budget_records(
        [
            _record(budget_id="BUDGET-2024-0001", total_amount=-5),
            _record(budget_id="BUDGET-2024-0002", client_name="TBD"),
        ]
    )
    result = validate_with_policy(df)
    assert result.discarded["budget_id"].tolist() == ["BUDGET-2024-0001"]
    # client_name admite nulos: "TBD" pasa; solo falla lo que la política manda a cuarentena.
    assert result.report["valid_rows"] == 1
