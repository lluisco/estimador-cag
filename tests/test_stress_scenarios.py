"""Los escenarios de stress son válidos para el endpoint y no disparan el detector de anclas."""

import pytest

from app.services.anchors import AnchorDetector
from evals.stress.scenarios import CHECKPOINTS, SCENARIOS, TOTAL_TURNS, fact_has_left_window

TRANSCRIPT_MIN_LENGTH = 20   # Form(min_length=20) en app/routers/sessions.py


@pytest.mark.parametrize("scenario", SCENARIOS.values(), ids=SCENARIOS.keys())
def test_scenario_shape(scenario):
    assert [t.turn_index for t in scenario.turns] == list(range(1, TOTAL_TURNS + 1))
    assert all(len(t.transcript) >= TRANSCRIPT_MIN_LENGTH for t in scenario.turns)
    declared = {t.fact for t in scenario.turns if t.fact}
    assert declared == set(scenario.fact_where)
    for turn in scenario.turns:
        if turn.fact:
            assert turn.fact.lower() in turn.transcript.lower()   # el fact está en el texto


@pytest.mark.parametrize("scenario", SCENARIOS.values(), ids=SCENARIOS.keys())
def test_no_turn_triggers_an_anchor(scenario):
    detector = AnchorDetector()
    assert [t.turn_index for t in scenario.turns if detector.is_anchor(t.transcript)] == []


def test_fact_leaves_window_only_after_k_plus_window():
    assert not fact_has_left_window(fact_turn=3, snapshot_turn=6)
    assert not fact_has_left_window(fact_turn=3, snapshot_turn=8)
    assert fact_has_left_window(fact_turn=3, snapshot_turn=9)
    assert [n for n in CHECKPOINTS if fact_has_left_window(3, n)] == [10, 20]
