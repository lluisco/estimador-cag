"""Política de validación: reparar / cuarentena / descartar.

Pandera puede abortar en el primer check que falla, pero en producción interesa la
lista completa de fallos: dice qué familia de suciedad ha golpeado la run. Con
``lazy=True`` se recogen todos y cada fila se reparte en una de tres cubetas:

* ``valid``: pasa todos los checks.
* ``quarantined``: fallo grave pero útil tras revisión humana (p. ej. ``client_name``
  nulo tras la limpieza). No entra al RAG; se guarda con su motivo.
* ``discarded``: contaminación clara (importe negativo, ``budget_id`` mal formado).
  Fuera, con log.

El ``report`` es serializable a JSON y funciona de alerta temprana: si una fuente se
degrada, se nota en el desglose por check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pandera.pandas as pa

from app.ingestion.cleaning.schemas import BudgetRecord

# Cuarentena: la fila PUEDE volver tras revisión manual.
QUARANTINE_CHECKS = {
    "not_nullable",  # p. ej. una fecha que la limpieza no pudo reparar (NaT)
    "no_default",
    "column_in_dataframe",
}
# Descarte: la fila es estructuralmente errónea.
DISCARD_CHECKS = {
    "in_range",
    "less_than_or_equal_to",
    "greater_than_or_equal_to",
    "isin",  # moneda fuera de {EUR, USD, GBP}
    "str_matches",  # budget_id o client_code mal formados
}


@dataclass
class ValidationResult:
    valid: pd.DataFrame
    quarantined: pd.DataFrame
    discarded: pd.DataFrame
    report: dict[str, Any] = field(default_factory=dict)


def validate_with_policy(df: pd.DataFrame) -> ValidationResult:
    """Pasa ``BudgetRecord`` sobre ``df`` y reparte las filas en tres cubetas."""
    empty = df.iloc[0:0].copy()
    if df.empty:
        return ValidationResult(df.copy(), empty, empty.copy(), {"input_rows": 0})

    # La limpieza deja columnas que el contrato no cubre (phases, contact, content_hash…).
    # Se valida solo lo que el schema define; si falta una columna del contrato, sigue fallando.
    contract_columns = [c for c in BudgetRecord.columns if c in df.columns]
    try:
        validated = BudgetRecord.validate(df[contract_columns], lazy=True)
    except pa.errors.SchemaErrors as err:
        return _route_failures(df, err)

    return ValidationResult(
        valid=df.loc[validated.index].copy(),
        quarantined=empty,
        discarded=empty.copy(),
        report={
            "input_rows": len(df),
            "valid_rows": len(validated),
            "quarantined_rows": 0,
            "discarded_rows": 0,
            "failures_by_check": {},
            "table_level_failures": [],
        },
    )


def _route_failures(df: pd.DataFrame, err: pa.errors.SchemaErrors) -> ValidationResult:
    quarantine_idx: set[int] = set()
    discard_idx: set[int] = set()
    failures_by_check: dict[str, int] = {}
    table_level_failures: list[str] = []

    for _, case in err.failure_cases.iterrows():
        check_name = str(case.get("check", "unknown"))
        failures_by_check[check_name] = failures_by_check.get(check_name, 0) + 1
        idx = case.get("index")
        if idx is None or pd.isna(idx):
            # Fallo de tabla (columna ausente, dtype erróneo): no es atribuible a una fila,
            # pero no puede perderse en silencio. Queda en el report para que alguien lo vea.
            table_level_failures.append(f"{check_name}: {case.get('failure_case')}")
            continue
        if any(name in check_name for name in DISCARD_CHECKS):
            discard_idx.add(int(idx))
        else:
            # QUARANTINE_CHECKS o un fallo desconocido: por seguridad, a revisión.
            quarantine_idx.add(int(idx))

    # Una fila con fallo de descarte siempre se descarta, aunque también falle uno de cuarentena.
    quarantine_idx -= discard_idx
    discarded_mask = df.index.isin(discard_idx)
    quarantined_mask = df.index.isin(quarantine_idx)
    valid_mask = ~(discarded_mask | quarantined_mask)

    return ValidationResult(
        valid=df.loc[valid_mask].copy(),
        quarantined=df.loc[quarantined_mask].copy(),
        discarded=df.loc[discarded_mask].copy(),
        report={
            "input_rows": len(df),
            "valid_rows": int(valid_mask.sum()),
            "quarantined_rows": int(quarantined_mask.sum()),
            "discarded_rows": int(discarded_mask.sum()),
            "failures_by_check": failures_by_check,
            "table_level_failures": table_level_failures,
        },
    )
