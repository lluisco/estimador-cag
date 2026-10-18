"""Métricas binarias del stress test: presupuestos de latencia y coste, y deriva de memoria.

Viven aquí y no en un ``evals/metrics.py`` porque no hay framework previo que extender y
porque dependen del shape de ``turn_observed`` (un dict de contadores) y del snapshot de
``GET /sessions/{id}``, no de un ``EstimationResult``. Replican el patrón ``MetricResult``
(name, score, passed, details). Deterministas: sin embeddings ni LLM-as-judge.
"""

from dataclasses import dataclass

VALID_WHERE = ("summary", "anchors", "metadata")


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: str


def _binary(name: str, ok: bool, details: str) -> MetricResult:
    return MetricResult(name=name, score=1.0 if ok else 0.0, passed=ok, details=details)


class LatencyBudgetMetric:
    """1.0 si latency_ms ≤ budget_ms; 0.0 si no. El límite exacto cumple."""

    def __init__(self, budget_ms: int):
        self.budget_ms = budget_ms

    def evaluate(self, observation: dict) -> MetricResult:
        latency = observation["latency_ms"]
        return _binary("latency_budget", latency <= self.budget_ms, f"{latency} ms (presupuesto {self.budget_ms} ms)")


class CostBudgetMetric:
    """1.0 si cost_usd ≤ budget_usd; 0.0 si no. El límite exacto cumple."""

    def __init__(self, budget_usd: float):
        self.budget_usd = budget_usd

    def evaluate(self, observation: dict) -> MetricResult:
        cost = observation["cost_usd"]
        return _binary("cost_budget", cost <= self.budget_usd, f"{cost} USD (presupuesto {self.budget_usd} USD)")


class MemoryDriftMetric:
    """1.0 si el fact aparece (case-insensitive) en summary, anchors o metadata del snapshot.

    El snapshot es la respuesta de ``GET /sessions/{id}``. Solo se busca en los textos de la
    metadata (no en enteros como ``assumed_team_size``) y los campos se separan con un salto
    de línea para que un fact no case a medias entre dos campos.

    Si el snapshot no trae ``memory`` (``EXPOSE_SESSION_DEBUG`` apagado) y se pide buscar en
    summary o anchors, lanza ``ValueError``: un 0.0 se leería como 'el sistema olvidó el dato'.
    """

    def __init__(self, fact: str, where: list[str] | None = None):
        where = list(VALID_WHERE) if where is None else list(where)
        unknown = set(where) - set(VALID_WHERE)
        if unknown:
            raise ValueError(f"'where' desconocido: {sorted(unknown)}; válidos: {VALID_WHERE}")
        if not fact.strip():
            raise ValueError("el fact no puede estar vacío")
        self.fact = fact
        self.where = where

    @staticmethod
    def _metadata_text(metadata: dict) -> str:
        parts: list[str] = []
        for value in metadata.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(item for item in value if isinstance(item, str))
        return "\n".join(parts)

    def _haystacks(self, snapshot: dict) -> dict[str, str]:
        memory = snapshot.get("memory")
        if memory is None and {"summary", "anchors"} & set(self.where):
            raise ValueError("el snapshot no incluye 'memory': activa EXPOSE_SESSION_DEBUG en el servidor")
        texts = {
            "summary": (memory or {}).get("summary", ""),
            "anchors": "\n".join((memory or {}).get("anchors", [])),
            "metadata": self._metadata_text(snapshot.get("project_metadata") or {}),
        }
        return {place: texts[place] for place in self.where}

    def evaluate(self, session_snapshot: dict) -> MetricResult:
        needle = self.fact.lower()
        found_in = [place for place, text in self._haystacks(session_snapshot).items() if needle in text.lower()]
        details = f"'{self.fact}' en {found_in}" if found_in else f"'{self.fact}' no aparece en {self.where}"
        return _binary("memory_drift", bool(found_in), details)
