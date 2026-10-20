"""Fábrica del ``AnalyzerEngine`` de Presidio configurado para español.

Por defecto Presidio monta spaCy en inglés: sobre "Laura Fernández" o "Javier
Romero" devuelve cero entidades PERSON. Y falla en silencio: el pipeline parece
funcionar y en producción alguien pregunta "¿qué dijo Laura Fernández?" y el LLM
responde con el nombre sin pseudonimizar. Un fallo así es peor que un falso
positivo porque nadie lo ve.

Este módulo es el único sitio que conecta Presidio con ``es_core_news_md``.
"""

from __future__ import annotations

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from app.config import settings
from app.ingestion.pii.recognizers import BudgetIdRecognizer, ClientCodeRecognizer


@lru_cache
def build_analyzer() -> AnalyzerEngine:
    """Devuelve el analyzer ligado al modelo español configurado (singleton).

    Singleton porque cargar spaCy tarda ~300 ms y Presidio es seguro entre hilos
    para análisis de solo lectura. Los recognizers propios se registran aquí para
    que nadie tenga que acordarse de hacerlo.
    """
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "es", "model_name": settings.PRESIDIO_SPACY_MODEL}],
        }
    )
    engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["es"])
    engine.registry.add_recognizer(BudgetIdRecognizer())
    engine.registry.add_recognizer(ClientCodeRecognizer())
    return engine
