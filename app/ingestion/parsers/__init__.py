"""Parsers: bytes → ``Document``.

``Parser`` es un ``typing.Protocol``, no una clase base: son funciones puras sobre
bytes y no deben heredar estado compartido.
"""

from app.ingestion.parsers.budget_json import BudgetJsonParser
from app.ingestion.parsers.protocol import ParseContext, Parser
from app.ingestion.parsers.registry import ParserRegistry, default_registry
from app.ingestion.parsers.transcript_txt import TranscriptTxtParser

__all__ = [
    "BudgetJsonParser",
    "ParseContext",
    "Parser",
    "ParserRegistry",
    "TranscriptTxtParser",
    "default_registry",
]
