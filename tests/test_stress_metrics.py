"""Métricas del stress test: una que pasa, una que falla y los casos límite de cada una."""

import pytest

from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric


def _snapshot(summary="", anchors=(), metadata=None, memory=True) -> dict:
    return {
        "project_metadata": metadata or {},
        "memory": {"summary": summary, "anchors": list(anchors)} if memory else None,
    }


# --- LatencyBudgetMetric / CostBudgetMetric ---------------------------------------------

def test_latency_passes_and_fails():
    metric = LatencyBudgetMetric(budget_ms=4000)
    assert metric.evaluate({"latency_ms": 1200}).passed
    failed = metric.evaluate({"latency_ms": 4001})
    assert (failed.score, failed.passed) == (0.0, False)


def test_latency_exactly_at_budget_passes():
    result = LatencyBudgetMetric(budget_ms=4000).evaluate({"latency_ms": 4000})
    assert (result.score, result.passed) == (1.0, True)


def test_cost_passes_and_fails():
    metric = CostBudgetMetric(budget_usd=0.01)
    assert metric.evaluate({"cost_usd": 0.0004}).passed
    assert not metric.evaluate({"cost_usd": 0.0101}).passed


def test_cost_exactly_at_budget_and_zero_pass():
    metric = CostBudgetMetric(budget_usd=0.01)
    assert metric.evaluate({"cost_usd": 0.01}).passed
    assert metric.evaluate({"cost_usd": 0.0}).passed


def test_budget_metric_fails_hard_on_missing_field():
    with pytest.raises(KeyError):
        LatencyBudgetMetric(4000).evaluate({"cost_usd": 0.1})


# --- MemoryDriftMetric ------------------------------------------------------------------

def test_fact_found_case_insensitive_and_reports_where():
    result = MemoryDriftMetric("Nimbus").evaluate(_snapshot(summary="El proyecto NIMBUS es de reservas"))
    assert result.passed and result.score == 1.0
    assert "summary" in result.details


def test_fact_lost_scores_zero():
    result = MemoryDriftMetric("30000").evaluate(_snapshot(summary="Presupuesto de 80000 EUR"))
    assert (result.score, result.passed) == (0.0, False)


def test_where_restricts_the_search():
    snapshot = _snapshot(summary="usa Flutter", metadata={"mentioned_technologies": ["React"]})
    assert MemoryDriftMetric("Flutter", where=["metadata"]).evaluate(snapshot).passed is False
    assert MemoryDriftMetric("React", where=["metadata"]).evaluate(snapshot).passed is True


def test_fact_found_in_anchors_and_in_metadata_list():
    assert MemoryDriftMetric("30000").evaluate(_snapshot(anchors=["presupuesto 30000 EUR"])).passed
    assert MemoryDriftMetric("Flutter").evaluate(_snapshot(metadata={"mentioned_technologies": ["Flutter"]})).passed


def test_integers_in_metadata_are_not_searched():
    snapshot = _snapshot(metadata={"assumed_team_size": 30000, "project_name": None})
    assert not MemoryDriftMetric("30000", where=["metadata"]).evaluate(snapshot).passed


def test_fact_does_not_match_across_fields():
    snapshot = _snapshot(metadata={"project_name": "Orion", "agreed_scope": "Flutter app"})
    assert not MemoryDriftMetric("OrionFlutter", where=["metadata"]).evaluate(snapshot).passed


def test_empty_snapshot_scores_zero_without_error():
    assert not MemoryDriftMetric("Nimbus").evaluate(_snapshot()).passed


def test_missing_memory_fails_hard_instead_of_scoring_zero():
    with pytest.raises(ValueError, match="EXPOSE_SESSION_DEBUG"):
        MemoryDriftMetric("Nimbus").evaluate(_snapshot(memory=False))


def test_metadata_only_search_works_without_memory():
    snapshot = _snapshot(metadata={"project_name": "Nimbus"}, memory=False)
    assert MemoryDriftMetric("Nimbus", where=["metadata"]).evaluate(snapshot).passed


def test_invalid_arguments_are_rejected():
    with pytest.raises(ValueError):
        MemoryDriftMetric("x", where=["resumen"])
    with pytest.raises(ValueError):
        MemoryDriftMetric("   ")
