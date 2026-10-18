from dataclasses import dataclass
from enum import StrEnum
import re

import structlog

from app.sessions import ProjectMetadata

log = structlog.get_logger()


class Tier(StrEnum):
    EXECUTIVE = "executive"
    PM = "pm"
    DEVELOPER = "developer"
    DEFAULT = "default"


_NDA = re.compile(r"\bnda\b|confidencialidad", re.IGNORECASE)
_REGULATION = re.compile(r"\b(rgpd|gdpr|hipaa|ens)\b|iso\s*27001", re.IGNORECASE)

_TECH_TERMS = (
    "api", "backend", "frontend", "base de datos", "microservicios", "kubernetes",
    "docker", "ci/cd", "oauth", "sql", "postgres", "redis", "react", "python",
    "aws", "azure", "endpoint", "webhook",
)

@dataclass(frozen=True)
class _Context:
    text: str                  # transcript + alcance + tecnologías
    team_size: int | None


def _distinct_tech_terms(text: str) -> int:
    found = {
        t for t in _TECH_TERMS
        if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.IGNORECASE)
    }
    return len(found)


# (nombre de la regla, tier que produce, condición). El ORDEN es la prioridad.
_RULES = (
    ("nda_detected", Tier.EXECUTIVE, lambda c: bool(_NDA.search(c.text))),
    ("regulation_detected", Tier.EXECUTIVE, lambda c: bool(_REGULATION.search(c.text))),
    ("technical_language", Tier.DEVELOPER, lambda c: _distinct_tech_terms(c.text) >= 2),
    ("small_team", Tier.PM, lambda c: c.team_size is not None and c.team_size <= 2),
)

def resolve_tier(
    transcript: str,
    metadata: ProjectMetadata,
    override: Tier | None = None,
) -> tuple[Tier, str]:
    if override is not None:
        return override, "caller_override"

    text = " ".join(
        [transcript, metadata.agreed_scope or "", *metadata.mentioned_technologies]
    )
    context = _Context(text=text, team_size=metadata.assumed_team_size)

    for name, tier, condition in _RULES:
        try:
            if condition(context):
                return tier, name
        except Exception as exc:
            log.warning("tier_rule_failed", rule=name, error=str(exc)[:200])

    return Tier.DEFAULT, "no_rule_matched"