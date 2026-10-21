# Sanity check de embeddings

Modelo: `text-embedding-3-small` (1536 dimensiones, dimensión por defecto).
Generado con `scripts/compare.py` dentro del contenedor (`docker compose exec servicio_ia ...`);
coseno calculado a mano con la biblioteca estándar. Fecha: 2026-10-21.

| Pareja | Texto A | Texto B | Coseno | Expectativa |
|--------|---------|---------|--------|-------------|
| A — cercanos | "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" | "Authorization service using JSON Web Tokens for a banking application" | **0.5957** | alta (> 0.6) |
| B — no relacionados | "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" | "Database migration from MySQL to PostgreSQL with zero downtime" | **0.1920** | baja (< 0.4) |
| C — genéricos | "Backend services" | "API development" | **0.5407** | sin expectativa fija |

## Comentario

- **B encaja con la intuición:** dos temas de ingeniería sin relación quedan en 0.19, muy por debajo de 0.4.
  El modelo separa claramente "autenticación para fintech" de "migración de base de datos".
- **A queda justo por debajo del umbral orientativo (0.5957 frente a 0.6)** aunque ambos textos describen
  lo mismo. Casi no comparten vocabulario (OAuth/JWT/fintech frente a Authorization/JSON Web Tokens/banking),
  así que el modelo tiene que tender el puente solo por significado. Aun así, la distancia a B (0.40 de
  diferencia) es lo que importa: discrimina bien; el 0.6 es una referencia, no una constante universal.
- **C es lo más llamativo:** dos frases cortas y genéricas ("Backend services" / "API development") puntúan
  0.5407, casi lo mismo que la pareja genuinamente cercana A. Un texto corto y vago aporta poca señal
  discriminante y "parece" cercano a casi cualquier cosa del mismo dominio. Es la razón de que el chunker
  anteponga la cabecera de contexto (proyecto + sector + tecnología) a cada componente, y buen material
  para discutir en el directo junto a las estrategias de chunking.
