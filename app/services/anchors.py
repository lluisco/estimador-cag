"""Detector de anclas (heurístico). Conservador a propósito: un falso positivo
deja el turno en el prompt para siempre; un falso negativo solo lo manda al resumen."""

import re

_PATTERNS = [
    # --- confidencialidad ---
    r"\bnda\b",
    r"acuerdo\s+de\s+confidencialidad",

    # --- contrato firmado ---
    r"contrato\s+(ya\s+)?(est[aá]\s+)?firmado",
    r"firm(amos|ado)\s+(el|un|nuestro)\s+contrato",

    # --- alcance cerrado ---
    r"alcance\s+(est[aá]\s+|queda\s+)?(cerrado|congelado)",
    r"(cerramos|congelamos)\s+el\s+alcance",

    # --- presupuesto cerrado ---
    r"presupuesto\s+(est[aá]\s+|queda\s+)?(cerrado|fijo)",
    r"presupuesto\s+m[aá]ximo",
    r"tope\s+de\s+\d",

    # --- regulación ---
    r"\b(rgpd|gdpr|hipaa|ens)\b",
    r"iso\s*27001",

    # --- fecha innegociable ---
    r"innegociable",
    r"tiene\s+que\s+estar\s+en\s+producci[oó]n\s+antes\s+de",

    # --- compromiso previo ---
    r"nos\s+comprometimos\s+a",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


class AnchorDetector:
    def is_anchor(self, user_message: str) -> bool:
        return any(p.search(user_message) for p in _COMPILED)