import pytest
from app.services.tier import Tier, resolve_tier
from app.sessions import ProjectMetadata

EMPTY = ProjectMetadata()


def test_default_when_nothing_matches():
    assert resolve_tier("quiero una app", EMPTY) == (Tier.DEFAULT, "no_rule_matched")

def test_nda_gives_executive():
    assert resolve_tier("firmamos un NDA", EMPTY) == (Tier.EXECUTIVE, "nda_detected")

def test_regulation_gives_executive():
    assert resolve_tier("cumple RGPD", EMPTY) == (Tier.EXECUTIVE, "regulation_detected")

def test_two_technical_terms_give_developer():
    assert resolve_tier("una API con Postgres", EMPTY) == (Tier.DEVELOPER, "technical_language")

def test_one_technical_term_is_not_enough():
    assert resolve_tier("una API simple", EMPTY)[0] == Tier.DEFAULT

def test_small_team_gives_pm():
    meta = ProjectMetadata(assumed_team_size=2)
    assert resolve_tier("quiero una app", meta) == (Tier.PM, "small_team")

def test_nda_beats_small_team():
    meta = ProjectMetadata(assumed_team_size=1)
    assert resolve_tier("hay un NDA", meta)[0] == Tier.EXECUTIVE

def test_override_beats_everything():
    meta = ProjectMetadata(assumed_team_size=1)
    assert resolve_tier("hay un NDA y RGPD", meta, Tier.DEVELOPER) == (Tier.DEVELOPER, "caller_override")

def test_nda_stored_in_metadata_still_counts():
    meta = ProjectMetadata(agreed_scope="Alcance cerrado bajo NDA")
    assert resolve_tier("¿cuánto tardaría?", meta)[0] == Tier.EXECUTIVE
