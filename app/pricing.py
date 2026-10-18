MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}


def _find_pricing(model: str) -> dict | None:
    """Exacto, o por prefijo: la API devuelve snapshots con fecha (``gpt-4o-mini-2024-07-18``,
    ``claude-haiku-4-5-20251001``) y la tabla guarda el nombre corto. Gana el prefijo más largo."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    prefixes = [name for name in MODEL_PRICING if model.startswith(f"{name}-")]
    return MODEL_PRICING[max(prefixes, key=len)] if prefixes else None


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = _find_pricing(model)
    if pricing is None:
        return None
    coste = (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000
    return round(coste, 6)