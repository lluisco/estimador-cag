import pytest
from pydantic import ValidationError

from app.schemas import EstimationResult, Phase


def _phase(weeks: int = 2, cost: int = 5000) -> Phase:
    return Phase(name="Fase", duration_weeks=weeks, cost_eur=cost, confidence_pct=80, assumptions=[])


def _result(**overrides) -> dict:
    data = {
        "summary": "Resumen",
        "total_duration_weeks": 4,
        "total_cost_eur": 10000,
        "confidence_pct": 70,
        "phases": [_phase(), _phase()],
    }
    data.update(overrides)
    return data


def test_totals_matching_phases_are_valid():
    assert EstimationResult(**_result()).total_cost_eur == 10000


def test_duration_tolerates_one_week_difference():
    EstimationResult(**_result(total_duration_weeks=5))


def test_duration_mismatch_is_rejected_with_actionable_message():
    with pytest.raises(ValidationError, match="total_duration_weeks is 8 but phases sum to 4"):
        EstimationResult(**_result(total_duration_weeks=8))


def test_cost_tolerates_two_percent_difference():
    EstimationResult(**_result(total_cost_eur=10150))


def test_cost_mismatch_is_rejected_with_actionable_message():
    with pytest.raises(ValidationError, match="total_cost_eur is 20000 but phases sum to 10000"):
        EstimationResult(**_result(total_cost_eur=20000))


def test_all_zero_costs_are_rejected_even_though_they_sum_to_the_total():
    zero_phases = [
        Phase(name="Fase", duration_weeks=2, cost_eur=1, confidence_pct=80, assumptions=[]).model_copy(
            update={"cost_eur": 0}
        )
    ]
    with pytest.raises(ValidationError):
        EstimationResult(**_result(total_duration_weeks=2, total_cost_eur=0, phases=zero_phases))


def test_empty_phases_are_rejected():
    with pytest.raises(ValidationError):
        EstimationResult(**_result(phases=[]))


@pytest.mark.parametrize(
    "field,value",
    [("duration_weeks", 0), ("duration_weeks", 53), ("confidence_pct", 101), ("cost_eur", -1), ("cost_eur", 0)],
)
def test_phase_bounds(field, value):
    data = {"name": "F", "duration_weeks": 2, "cost_eur": 100, "confidence_pct": 50, "assumptions": []}
    data[field] = value
    with pytest.raises(ValidationError):
        Phase(**data)
