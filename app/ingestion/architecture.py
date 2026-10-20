"""Decisión de arquitectura: ¿CAG, RAG o híbrido?

Forma ejecutable de la decisión del artículo 1. No está en el camino de las
peticiones de FastAPI: es un CLI para razonar sobre el corpus antes de ingerir.

    python -m app.ingestion.architecture

Dos piezas:

* ``CAGViability``: las cuatro restricciones del CAG (ventana de contexto, coste,
  latencia, lost-in-the-middle). ``viable`` es un AND a propósito: un solo eje en
  rojo tumba el CAG.
* ``recommend_architecture``: evalúa los cuatro ejes de decisión (volumen,
  frecuencia de refresco, trazabilidad, control de acceso) y devuelve
  ``"CAG" | "Hybrid" | "RAG"``.

El fine-tuning no aparece: es una capa ortogonal (enseña cómo responder, no
aporta datos nuevos ni resuelve la trazabilidad).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

# Por encima de este volumen asumimos que el modelo ya no "usa el centro" y que la
# latencia se sale del SLO.
_CENTER_RECALL_TOKEN_BUDGET = 100_000
# El corpus solo cabe en CAG si deja holgura en la ventana (usamos el 70 %).
_USABLE_WINDOW_FRACTION = 0.7
# El prefix caching solo compensa si el corpus es estable al menos una semana.
_CACHE_FRIENDLY_REFRESH_DAYS = 7


@dataclass
class CAGViability:
    """Las cuatro restricciones del CAG. ``viable`` es el AND de todas."""

    context_window_ok: bool  # ¿cabe el corpus completo en la ventana?
    cost_ok: bool  # ¿el coste por turno con prefix caching es asumible?
    latency_ok: bool  # ¿la latencia con el corpus completo se queda bajo el SLO?
    lost_in_the_middle_ok: bool  # ¿el modelo USA el centro del contexto?

    @property
    def viable(self) -> bool:
        return all(
            [
                self.context_window_ok,
                self.cost_ok,
                self.latency_ok,
                self.lost_in_the_middle_ok,
            ]
        )

    def failing_constraints(self) -> list[str]:
        """Nombres de las restricciones en rojo; vacío si y solo si ``viable``."""
        return [
            name
            for name, ok in (
                ("context_window", self.context_window_ok),
                ("cost", self.cost_ok),
                ("latency", self.latency_ok),
                ("lost_in_the_middle", self.lost_in_the_middle_ok),
            )
            if not ok
        ]


@dataclass
class CorpusProfile:
    name: str
    estimated_tokens: int  # volumen total estimado
    refresh_frequency_days: float  # cada cuánto cambian los datos
    traceability_required: bool  # ¿hay que poder citar la fuente?
    access_control_required: bool  # ¿hay que filtrar por permisos de usuario?


@dataclass
class ModelProfile:
    name: str
    context_window: int  # tokens
    cost_per_1k_input: float  # USD
    prefix_caching: bool  # ¿soporta caché de prefijo?


def assess_cag_viability(corpus: CorpusProfile, model: ModelProfile) -> CAGViability:
    """Deriva las cuatro restricciones a partir de los perfiles de corpus y modelo.

    Heurísticas simples a propósito: el objetivo es didáctico, no un modelo de coste calibrado.
    """
    fits = corpus.estimated_tokens <= model.context_window * _USABLE_WINDOW_FRACTION
    return CAGViability(
        context_window_ok=fits,
        cost_ok=model.prefix_caching
        and corpus.refresh_frequency_days >= _CACHE_FRIENDLY_REFRESH_DAYS,
        latency_ok=corpus.estimated_tokens <= _CENTER_RECALL_TOKEN_BUDGET,
        lost_in_the_middle_ok=corpus.estimated_tokens <= _CENTER_RECALL_TOKEN_BUDGET,
    )


def recommend_architecture(
    corpus: CorpusProfile, model: ModelProfile
) -> Literal["CAG", "Hybrid", "RAG"]:
    """Recomienda una arquitectura sobre los cuatro ejes de decisión."""
    # Eje 1, volumen: ¿cabe con holgura en la ventana?
    fits_in_window = corpus.estimated_tokens <= model.context_window * _USABLE_WINDOW_FRACTION
    # Eje 2, frecuencia: cambios más frecuentes que semanales rompen el prefix caching.
    cache_friendly = corpus.refresh_frequency_days >= _CACHE_FRIENDLY_REFRESH_DAYS
    # Eje 3, trazabilidad: sin retriever no hay metadata de fuente que citar.
    traceability_doable = not corpus.traceability_required
    # Eje 4, acceso: CAG no filtra por usuario antes del prompt.
    access_control_doable = not corpus.access_control_required

    if all([fits_in_window, cache_friendly, traceability_doable, access_control_doable]):
        return "CAG"
    # Si cabe y es estable pero falla trazabilidad o acceso, el híbrido
    # (CAG para lo estable, RAG para lo citable o sensible) es razonable.
    if fits_in_window and cache_friendly:
        return "Hybrid"
    return "RAG"


# --- Proyecto 2, con números defendibles ---

PROYECTO_2 = CorpusProfile(
    name="Proyecto 2",
    estimated_tokens=250_000,  # presupuestos + transcripciones + tarifas + adendas
    refresh_frequency_days=7,  # cierre comercial semanal
    traceability_required=True,  # legal exige citar la fuente
    access_control_required=True,  # información confidencial de clientes
)

CURRENT_MODEL = ModelProfile(
    name="gpt-4o-mini",
    context_window=128_000,
    cost_per_1k_input=0.00015,
    prefix_caching=True,
)


def _main() -> int:
    """CLI: ``python -m app.ingestion.architecture``."""
    corpus, model = PROYECTO_2, CURRENT_MODEL
    viability = assess_cag_viability(corpus, model)

    print(
        f"Corpus '{corpus.name}': {corpus.estimated_tokens:,} tokens, "
        f"refresh cada {corpus.refresh_frequency_days:g} días, "
        f"trazabilidad={corpus.traceability_required}, "
        f"control_acceso={corpus.access_control_required}"
    )
    print(
        f"Modelo '{model.name}': ventana {model.context_window:,} tokens, "
        f"prefix_caching={model.prefix_caching}"
    )
    print()
    if viability.viable:
        print("Viabilidad CAG: viable (las 4 restricciones en verde)")
    else:
        print("Viabilidad CAG: NO viable")
        print(f"  Restricciones en rojo: {', '.join(viability.failing_constraints())}")
    print(f"Recomendación arquitectónica: {recommend_architecture(corpus, model)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
