"""Schema Pandera v2 del DataFrame de presupuestos ya limpio.

Ojo con el import de Pandera v2: ``import pandera.pandas as pa``; en v1 era
``import pandera as pa``. Esta migración rompió muchos tutoriales.

Es el contrato de contenido, el equivalente para datos de lo que
``data_catalog.yaml`` es para las fuentes: un único fichero versionado.
``strict=True`` rechaza columnas desconocidas y ``coerce=False`` porque la
limpieza ya convirtió los tipos. Lo que se relaja es la política, no el contrato.
"""

from __future__ import annotations

from pandera.pandas import Check, Column, DataFrameSchema

BUDGET_ID_PATTERN = r"^BUDGET-\d{4}-\d{4}$"
CLIENT_CODE_PATTERN = r"^CLI-\d{4}$"

BudgetRecord: DataFrameSchema = DataFrameSchema(
    columns={
        "budget_id": Column(str, checks=Check.str_matches(BUDGET_ID_PATTERN), nullable=False),
        # La limpieza convierte TBD/N/A en NA: va a cuarentena, no se descarta.
        "client_name": Column(str, nullable=True),
        "client_code": Column(str, checks=Check.str_matches(CLIENT_CODE_PATTERN), nullable=False),
        "currency": Column(str, checks=Check.isin(["EUR", "USD", "GBP"]), nullable=False),
        "total_amount": Column(float, checks=[Check.ge(0), Check.le(10_000_000)], nullable=False),
        "signed_at": Column("datetime64[ns]", nullable=False),
    },
    strict=True,
    coerce=False,
)
