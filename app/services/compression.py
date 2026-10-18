from app.services.anchors import AnchorDetector
from app.services.summarizer import CumulativeSummarizer
from app.sessions import ConversationHistory

class CompressionPolicy:
    def __init__(self, detector: AnchorDetector, summarizer: CumulativeSummarizer):
        self._detector = detector
        self._summarizer = summarizer

    def apply(self, history: ConversationHistory) -> None:
        expelled: list[tuple[dict, dict]] = []

        while history.turns > history.max_turns:
            user, assistant = history.pop_oldest_turn()
            if self._detector.is_anchor(user["content"]):
                history.anchors.extend([user, assistant])
            else:
                expelled.append((user, assistant))

        if expelled:
            history.summary = self._summarizer.summarize(history.summary, expelled)