import pytest
from app.services.anchors import AnchorDetector

@pytest.mark.parametrize("text", [
    "Firmamos un NDA con el cliente",
    "El contrato ya está firmado",
    "El alcance está congelado",
    "El presupuesto está cerrado en 40.000 €",
    "Tiene que cumplir RGPD",
    "Necesitamos ISO 27001",
    "La fecha es innegociable",
    "Nos comprometimos a entregar en marzo",
])
def test_detects_anchors(text):
    assert AnchorDetector().is_anchor(text)

@pytest.mark.parametrize("text", [
    "Quiero una app de reservas",
    "Habrá un contrato en algún momento",
    "¿Puedes darme un presupuesto aproximado?",
    "Usaremos React y Postgres",
])
def test_ignores_normal_messages(text):
    assert not AnchorDetector().is_anchor(text)