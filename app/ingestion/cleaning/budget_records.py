"""Limpieza reparable vista tabular de los presupuestos.

Cinco pasos, en este orden, sobre un DataFrame que se trata como crudo:

1. **Nulos disfrazados**: ``"TBD"``, ``"N/A"``, cadenas vacías → ``pd.NA``. Son la
   suciedad más fácil de pasar por alto y la más difícil de depurar después.
2. **Moneda**: ``EUR`` y ``eur`` se colapsan a mayúsculas. Otras monedas se
   conservan (la validación las cazará).
3. **Fechas**: ``signed_at`` llega como ISO ``2024-05-02`` o como ``12/03/2024``.
   Con ``errors="coerce"`` lo no parseable queda en ``NaT`` y decide la validación.
4. **Numéricos**: ``total_amount`` a número con ``errors="coerce"``; los strings se
   cuelan desde exportaciones manuales.
5. **Dedup**: ante el mismo ``budget_id`` con contenido distinto, la política (que
   vive aquí, en código) es quedarse con el ``signed_at`` más reciente. Es una
   decisión de negocio, no técnica, y documentarla forma parte del entregable.

La entrada son los registros JSON originales, no el markdown de ``Document.text``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import pandas as pd

NULL_PLACEHOLDERS = {"TBD", "N/A", "n/a", "tbd", "", "null", "None", "-"}
_NULLABLE_TEXT_COLUMNS = ("client_name", "contact", "contact_email", "notes")


def clean_budget_records(records: Iterable[dict]) -> pd.DataFrame:
    """Devuelve el DataFrame limpio a partir de la lista de dicts de presupuestos."""
    df = pd.DataFrame(list(records))
    if df.empty:
        return df

    for column in _NULLABLE_TEXT_COLUMNS:
        if column in df.columns:
            df[column] = df[column].apply(
                lambda v: pd.NA if isinstance(v, str) and v.strip() in NULL_PLACEHOLDERS else v
            )

    if "currency" in df.columns:
        df["currency"] = df["currency"].astype("string").str.upper()

    if "signed_at" in df.columns:
        df["signed_at"] = pd.to_datetime(df["signed_at"], errors="coerce", dayfirst=True)

    if "total_amount" in df.columns:
        # float explícito: el schema usa coerce=False y un int64 limpio fallaría el dtype.
        df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").astype("float64")

    if {"budget_id", "signed_at"}.issubset(df.columns):
        df["content_hash"] = df.apply(_content_hash, axis=1)
        # El signed_at más reciente queda el último por budget_id y es el que sobrevive.
        df = df.sort_values(by=["budget_id", "signed_at"], na_position="first")
        df = df.drop_duplicates(subset=["budget_id"], keep="last").reset_index(drop=True)

    return df


def _content_hash(row: pd.Series) -> str:
    """JSON canónico de la fila → sha256 (los NaN se normalizan a ``None``)."""
    payload = {
        k: None if isinstance(v, float) and pd.isna(v) else _serializable(v)
        for k, v in row.items()
        if k != "content_hash"
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _serializable(value):
    return value.isoformat() if isinstance(value, pd.Timestamp) else value
