"""Capa de pseudonimización conforme a GDPR.

* ``analyzer``: el ``AnalyzerEngine`` de Presidio con el modelo spaCy en español.
* ``recognizers``: patrones propios del dominio (``BUDGET_ID``, ``CLIENT_CODE``).
* ``pseudonymizer``: el ``ConsistentPseudonymizer``. Mismo valor → mismo
  pseudónimo, entre documentos y entre ejecuciones, respaldado por una
  ``MappingStore`` persistente que lo hace reversible (art. 17).

Va después de la validación y antes del chunking, y se activa con la sensibilidad
declarada en el catálogo.
"""

from app.ingestion.pii.analyzer import build_analyzer
from app.ingestion.pii.mapping_store import InMemoryMappingStore, MappingStore, PostgresMappingStore
from app.ingestion.pii.pseudonymizer import ConsistentPseudonymizer, PseudonymizationResult
from app.ingestion.pii.recognizers import BudgetIdRecognizer, ClientCodeRecognizer

__all__ = [
    "BudgetIdRecognizer",
    "ClientCodeRecognizer",
    "ConsistentPseudonymizer",
    "InMemoryMappingStore",
    "MappingStore",
    "PostgresMappingStore",
    "PseudonymizationResult",
    "build_analyzer",
]
