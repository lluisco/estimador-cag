from app.services.anchors import AnchorDetector
from app.services.compression import CompressionPolicy
from app.services.summarizer import CumulativeSummarizer
from app.sessions import ConversationHistory


class SpySummarizer:
    def __init__(self):
        self.calls = []

    def summarize(self, previous, expelled):
        self.calls.append((previous, expelled))
        return f"resumen de {len(expelled)}"


def _history(texts, max_turns=2):
    h = ConversationHistory(max_turns=max_turns)
    for t in texts:
        h.add_turn(t, "ok")
    return h


def test_does_nothing_under_the_limit():
    spy = SpySummarizer()
    h = _history(["uno", "dos"])
    CompressionPolicy(AnchorDetector(), spy).apply(h)
    assert spy.calls == [] and h.summary is None and h.anchors == []


def test_normal_expelled_turn_goes_to_summarizer():
    spy = SpySummarizer()
    h = _history(["uno", "dos", "tres"])
    CompressionPolicy(AnchorDetector(), spy).apply(h)
    assert len(spy.calls) == 1
    assert h.summary == "resumen de 1"
    assert h.turns == 2


def test_anchor_skips_the_summarizer():
    spy = SpySummarizer()
    h = _history(["firmamos un NDA", "dos", "tres"])
    CompressionPolicy(AnchorDetector(), spy).apply(h)
    assert spy.calls == []                       # nunca se resumió
    assert h.anchors[0]["content"] == "firmamos un NDA"
    assert len(h.anchors) == 2                   # el par completo


def test_applying_twice_changes_nothing():
    spy = SpySummarizer()
    h = _history(["uno", "dos", "tres", "cuatro"])
    policy = CompressionPolicy(AnchorDetector(), spy)
    policy.apply(h)
    snapshot = (h.summary, list(h.anchors), h.messages)
    policy.apply(h)
    assert (h.summary, list(h.anchors), h.messages) == snapshot
    assert len(spy.calls) == 1


def test_several_expelled_turns_use_one_call():
    spy = SpySummarizer()
    h = _history(["a", "b", "c", "d", "e"])      # sobran 3
    CompressionPolicy(AnchorDetector(), spy).apply(h)
    assert len(spy.calls) == 1
    assert len(spy.calls[0][1]) == 3

def test_summarizer_failure_keeps_previous(fake_wrapper):
    fake_wrapper.summary_error = RuntimeError("caído")
    s = CumulativeSummarizer(fake_wrapper, "modelo")
    out = s.summarize("resumen previo", [({"content": "x"}, {"content": "y"})])
    assert out == "resumen previo"