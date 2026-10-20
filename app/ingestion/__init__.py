"""Subsistema de ingesta (sesión 6).

Tres capas, cada una en su subpaquete:

* ``catalog``: auditoría versionada de las fuentes (qué ingerimos y por qué).
* ``loaders`` + ``parsers``: bytes crudos → ``Document`` canónico.
* ``cleaning`` + ``pii``: validación tabular y pseudonimización GDPR.

El punto de entrada HTTP vive en ``app.routers.ingestion`` y el pegamento offline
en ``app.ingestion.orchestrator``.
"""
