"""analyze.py convierte el CSV del runner en las tablas del informe."""

import pytest

from evals.stress.analyze import build, load, percentile
from evals.stress.run import parse_args, run


def test_percentile_interpolates_and_handles_edges():
    assert percentile([], 0.5) is None
    assert percentile([7], 0.95) == 7
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([0, 100], 0.95) == 95


@pytest.fixture
def fake_csv(tmp_path):
    from app.main import app
    out = tmp_path / "r.csv"
    assert run(parse_args(["--fake", "--output", str(out), "--repeats", "2", "--max-turns", "10",
                           "--scenarios", "contradiction", "--attachment-sizes", "0,5"])) == 0
    app.dependency_overrides.clear()
    return out


def test_build_has_every_section_and_measures_recall(fake_csv):
    text = build(load(fake_csv))
    for section in ("Tabla resumen", "Curva 1", "Curva 2", "Curva 3", "Adjuntos", "Otros datos"):
        assert f"## {section}" in text
    # N=10: el fact del turno 1 (Kestrel) ya salió de la ventana y se evalúa en las 2 repeticiones
    recall_row = next(l for l in text.splitlines() if l.startswith("| contradiction | 10 |"))
    assert "| 4 |" in recall_row or "| 2 |" in recall_row
