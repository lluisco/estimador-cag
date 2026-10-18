"""Genera los PDFs sintéticos del escenario de adjuntos grandes.

El tamaño se calibra en CARACTERES DE TEXTO EXTRAÍDO, no en bytes del archivo: es lo que
recorta ``MAX_ATTACHMENT_CHARS`` y lo que llega al prompt. Con ~2 500 caracteres por
página (la proporción de la guía): 5 KB ≈ 2 páginas, 20 KB ≈ 8, 50 KB ≈ 20, 100 KB ≈ 40.

Son determinísticos (texto cíclico, sin azar, fecha de creación fija), así que no se
comitean: el runner los regenera con ``build_all``.

Cada PDF lleva tres "canarios", requisitos con un nombre propio inventado, colocados al
principio, en el medio y al final. Con el recorte de 60 000 caracteres, el PDF de 100 KB
conserva el primero y el segundo y pierde el tercero: el recall de cada canario en la
respuesta mide qué parte del adjunto llega al LLM y cuál se usa.

    uv run python -m evals.stress.fixtures.build_pdfs [directorio]
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

FIXTURES_DIR = Path(__file__).parent

# etiqueta del tamaño -> caracteres de texto objetivo (0 = sin adjunto, no se genera PDF)
SIZES_CHARS = {5: 5_000, 20: 20_000, 50: 50_000, 100: 100_000}

# posición relativa en el texto -> nombre propio que debería aparecer en la respuesta
CANARIES = {"start": "Zafiro", "middle": "Cobalto", "end": "Ambar"}
_CANARY_SENTENCES = {
    "start": "Requisito clave: el sistema debe integrarse con el ERP Zafiro de la empresa.",
    "middle": "Requisito clave: los cobros se harán a través de la pasarela Cobalto.",
    "end": "Requisito clave: el acceso fisico se controlara con los lectores Ambar.",
}

# Texto de relleno neutro (ASCII: la fuente Helvetica integrada solo cubre latin-1).
_FILLER = [
    "El sistema debe registrar cada operacion con fecha, hora y usuario responsable.",
    "Los informes se generaran bajo demanda y podran filtrarse por periodo y por categoria.",
    "La interfaz seguira las guias de accesibilidad y funcionara en los navegadores actuales.",
    "Los datos se almacenaran en una base de datos relacional con copias de seguridad diarias.",
    "Cada modulo expondra una API documentada para facilitar futuras integraciones.",
    "El equipo realizara revisiones de codigo y pruebas automaticas antes de cada entrega.",
    "Las notificaciones se enviaran por correo electronico segun las preferencias del usuario.",
    "El rendimiento esperado es de respuesta inferior a dos segundos en el percentil noventa.",
    "La documentacion tecnica se mantendra actualizada junto con el codigo fuente.",
    "Los permisos se gestionaran por roles, con un administrador por cada organizacion.",
]


def _text_with_canaries(target_chars: int) -> str:
    """Texto cíclico de ``target_chars`` caracteres con los tres canarios insertados."""
    marks = {int(target_chars * 0.02): "start", int(target_chars * 0.50): "middle", int(target_chars * 0.97): "end"}
    out: list[str] = []
    length = 0
    i = 0
    pending = sorted(marks)
    while length < target_chars:
        if pending and length >= pending[0]:
            sentence = _CANARY_SENTENCES[marks[pending.pop(0)]]
        else:
            sentence = _FILLER[i % len(_FILLER)]
            i += 1
        out.append(sentence)
        length += len(sentence) + 1
    return " ".join(out)


def build_pdf(target_chars: int, path: Path) -> Path:
    pdf = FPDF()
    pdf.set_creation_date(datetime(2025, 1, 1, tzinfo=timezone.utc))   # reproducible
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 5.5, _text_with_canaries(target_chars))
    pdf.output(str(path))
    return path


def build_all(out_dir: Path = FIXTURES_DIR) -> dict[int, Path]:
    """Genera ``attach_{kb}kb.pdf`` para cada tamaño y devuelve ``{kb: ruta}``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return {kb: build_pdf(chars, out_dir / f"attach_{kb}kb.pdf") for kb, chars in SIZES_CHARS.items()}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURES_DIR
    for kb, path in build_all(target).items():
        print(f"{kb:>3} KB -> {path} ({path.stat().st_size} bytes en disco)")
