import re
import unicodedata
from functools import lru_cache
from typing import Literal

import structlog
from openai import OpenAI, OpenAIError

from app.config import settings

log = structlog.get_logger()


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    # Lazy: no exige credenciales al importar el módulo.
    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=10.0)

Reason = Literal["prompt_injection", "pii", "moderation"]

class InputGuardrailViolation(Exception):
    def __init__(self, message: str, *, reason: Reason) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason

# Prompt injection: se aplican sobre el texto normalizado (minúsculas, sin tildes,
# espacios colapsados), así que "IGNORA   las instrucciónes" también casa.
PROMPT_INJECTION_PATTERNS = [
    # inglés
    re.compile(r"ignore (all |any )?(the )?(previous|prior|above|earlier)"),
    re.compile(r"ignore (all |any )?(the )?(your )?instructions"),
    re.compile(r"disregard (all |any )?(the )?(previous|prior|above|your)"),
    re.compile(r"you are now"),
    re.compile(r"system prompt"),
    # español
    re.compile(r"ignora (todas |todo |cualquier )?(las |los |tus )?(instrucciones|indicaciones|reglas|ordenes)"),
    re.compile(r"ignora (lo )?(anterior|previo)"),
    re.compile(r"olvida (todas |todo )?(las |tus )?(instrucciones|reglas|anterior)"),
    re.compile(r"ahora eres"),
    re.compile(r"prompt (del )?sistema"),
    # romper la estructura de la plantilla
    re.compile(r"</?\s*project_description\s*>"),
]

# PII patterns
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
# Phone: solo formatos que parecen un teléfono real, para no marcar importes, IDs o fechas.
#  - internacional: prefijo + o 00 seguido de 9-13 dígitos (con separadores opcionales)
#  - nacional (ES): 9 dígitos empezando por 6-9, agrupados 3-3-3, 3-2-2-2 o 2-3-2-2 con
#    separador consistente (espacio o guion), o 9 dígitos seguidos.
_PHONE_RE = re.compile(
    r"(?<![\w.,+-])(?:"
    r"(?:\+|00)\d{1,3}(?:[\s.-]?\d){8,12}"
    r"|[6-9]\d{2}(?P<s1>[\s-])\d{3}(?P=s1)\d{3}"
    r"|[6-9]\d{2}(?P<s2>[\s-])\d{2}(?P=s2)\d{2}(?P=s2)\d{2}"
    r"|[6-9]\d(?P<s3>[\s-])\d{3}(?P=s3)\d{2}(?P=s3)\d{2}"
    r"|[6-9]\d{8}"
    r")(?![\w.,-]?\d)"
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower())


def check_prompt_injection(description: str) -> None:
    normalized = _normalize(description)
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(normalized):
            raise InputGuardrailViolation(
                f"Description contains disallowed pattern: {pattern.pattern}", reason="prompt_injection"
            )


def check_email(description: str) -> None:
    if _EMAIL_RE.search(description):
        raise InputGuardrailViolation("Description contains an email address", reason="pii")


def check_iban(description: str) -> None:
    if _IBAN_RE.search(description):
        raise InputGuardrailViolation("Description contains an IBAN", reason="pii")


def check_phone(description: str) -> None:
    if _PHONE_RE.search(description):
        raise InputGuardrailViolation("Description contains a phone number", reason="pii")


def check_moderation(description: str) -> None:
    try:
        moderation = _get_client().moderations.create(input=description)
    except OpenAIError as e:
        # fail-open: moderation es una capa extra; los checks locales ya se han aplicado.
        log.warning("moderation_unavailable", error_type=type(e).__name__)
        return
    if moderation.results[0].flagged:
        raise InputGuardrailViolation("Description flagged by moderation API", reason="moderation")


def validate_input(description: str) -> None:
    # Primero los checks locales y baratos; la llamada de red a moderation al final.
    check_prompt_injection(description)
    check_email(description)
    check_iban(description)
    check_phone(description)
    check_moderation(description)
