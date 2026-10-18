"""calculate_cost reconoce los snapshots con fecha que devuelve la API."""

import pytest

from app.pricing import calculate_cost


@pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4o-mini-2024-07-18"])
def test_dated_snapshot_costs_the_same_as_the_short_name(model):
    assert calculate_cost(model, 1_000_000, 1_000_000) == 0.75


def test_haiku_snapshot_is_priced():
    assert calculate_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0


def test_unknown_model_is_not_priced_as_zero():
    assert calculate_cost("gpt-4o", 100, 100) is None
    assert calculate_cost("gpt-4o-minimal", 100, 100) is None   # no es un snapshot de gpt-4o-mini
