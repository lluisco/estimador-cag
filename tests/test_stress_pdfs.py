"""Los PDFs sintéticos están calibrados en texto extraído y son reproducibles."""

import pytest

from app.config import settings
from app.services.attachments import _extract_pdf
from evals.stress.fixtures.build_pdfs import CANARIES, SIZES_CHARS, build_all


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    return build_all(tmp_path_factory.mktemp("pdfs"))


@pytest.mark.parametrize("kb", SIZES_CHARS)
def test_extracted_chars_match_target(pdfs, kb):
    text = _extract_pdf(pdfs[kb].read_bytes()).strip()
    assert SIZES_CHARS[kb] <= len(text) <= SIZES_CHARS[kb] * 1.05


def test_truncation_keeps_start_and_middle_but_loses_end_only_at_100kb(pdfs):
    def kept(kb):
        return _extract_pdf(pdfs[kb].read_bytes()).strip()[: settings.MAX_ATTACHMENT_CHARS]

    for kb in (5, 20, 50):
        assert all(name in kept(kb) for name in CANARIES.values())
    text_100 = kept(100)
    assert CANARIES["start"] in text_100 and CANARIES["middle"] in text_100
    assert CANARIES["end"] not in text_100


def test_pdfs_are_deterministic(pdfs, tmp_path):
    again = build_all(tmp_path)
    assert all(pdfs[kb].read_bytes() == again[kb].read_bytes() for kb in pdfs)
