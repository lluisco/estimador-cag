"""Capa de limpieza y validación.

Dos pasadas, deliberadamente separadas:

* ``budget_records.clean_budget_records``: arreglos con pandas (nulos disfrazados,
  moneda, coerción permisiva, dedup). Repara lo reparable, no juzga.
* ``policy.validate_with_policy``: checks de Pandera que reparten las filas en
  válidas, en cuarentena y descartadas. Decide qué entra.

La limpieza da forma a los datos; la validación hace de portero.
"""

from app.ingestion.cleaning.budget_records import clean_budget_records
from app.ingestion.cleaning.policy import ValidationResult, validate_with_policy
from app.ingestion.cleaning.schemas import BudgetRecord

__all__ = [
    "BudgetRecord",
    "ValidationResult",
    "clean_budget_records",
    "validate_with_policy",
]
