MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    coste = (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000
    return round(coste, 6)