"""Recognizers propios del dominio para Presidio.

Presidio detecta PERSON, EMAIL, LOCATION… de fábrica, pero el corpus del
Proyecto 2 trae además:

* **BUDGET_ID**: ``BUDGET-YYYY-NNNN``. Revela volumen comercial.
* **CLIENT_CODE**: ``CLI-NNNN``. Corresponde uno a uno con clientes reales.

Son patrones deterministas con score alto (0,95): un regex muy específico gana en
un solape a una detección genérica de NER (0,4-0,6). Sin recognizer propio, estos
identificadores se vectorizarían en claro.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class BudgetIdRecognizer(PatternRecognizer):
    """Detecta identificadores ``BUDGET-YYYY-NNNN``."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BUDGET_ID",
            name="BudgetIdRecognizer",
            patterns=[Pattern(name="budget_id_pattern", regex=r"\bBUDGET-\d{4}-\d{4}\b", score=0.95)],
            supported_language="es",
        )


class ClientCodeRecognizer(PatternRecognizer):
    """Detecta códigos de cliente ``CLI-NNNN``."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CLIENT_CODE",
            name="ClientCodeRecognizer",
            patterns=[Pattern(name="client_code_pattern", regex=r"\bCLI-\d{4}\b", score=0.95)],
            supported_language="es",
        )
