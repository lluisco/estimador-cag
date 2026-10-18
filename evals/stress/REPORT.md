# Stress test del CAG: línea base cuantitativa

**Setup.** Servicio de sesiones con ventana deslizante de 6 turnos, anclas por regex, resumen acumulativo y `ProjectMetadata`. Un único proveedor (`gpt-4o-mini`, fijado con `FALLBACK_MODEL`: el `Router` reparte la carga entre los dos modelos configurados, no hace failover). 3 escenarios × 20 turnos y 5 tamaños de adjunto, 3 repeticiones, hasta 3 reintentos por turno ante un 5xx. 195 turnos, 0,23 USD. Datos: `results.csv`; tablas generadas con `analyze.py`.

## 1. Resumen

| escenario | adjunto | turnos | errores | P50 ms | P95 ms | coste total USD | hit exact | hit semantic | recall medio (facts evaluados) |
|---|---|---|---|---|---|---|---|---|---|
| growing | – | 60 | 1 | 5,687 | 10,327 | 0.0523 | 0% | 0% | 0.99 (113) |
| pivot | – | 60 | 2 | 7,368 | 19,555 | 0.0745 | 0% | 0% | 1.00 (105) |
| contradiction | – | 60 | 2 | 7,860 | 18,327 | 0.0689 | 0% | 0% | 0.67 (93) |
| attachments | 0 KB | 3 | 0 | 4,115 | 4,182 | 0.0016 | 0% | 0% | n/a |
| attachments | 5 KB | 3 | 0 | 4,096 | 4,228 | 0.0027 | 0% | 0% | n/a |
| attachments | 20 KB | 3 | 0 | 4,469 | 5,024 | 0.0056 | 0% | 0% | n/a |
| attachments | 50 KB | 3 | 0 | 5,011 | 6,151 | 0.0133 | 0% | 0% | n/a |
| attachments | 100 KB | 3 | 0 | 5,603 | 7,383 | 0.0132 | 0% | 0% | n/a |

Los hits de caché son 0 % por construcción: el camino de sesiones no usa `EstimationCache` ni existe caché semántica. Con n = 3 por celda de adjunto, el P95 es casi el máximo.

## 2. Las tres curvas

**Latencia vs `tokens_in`** (turnos de los tres escenarios y de los adjuntos).

| tokens_in | n | tokens_out medio | P50 ms | P95 ms |
|---|---|---|---|---|
| 0–3,000 | 28 | 230 | 3,088 | 5,856 |
| 3,000–5,000 | 117 | 537 | 6,605 | 10,119 |
| 5,000–8,000 | 17 | 1,029 | 12,208 | 14,795 |
| 8,000–12,000 | 19 | 1,501 | 17,784 | 19,400 |
| 12,000–20,000 | 3 | 2,304 | 22,925 | 23,510 |
| ≥ 20,000 | 6 | 327 | 5,307 | 7,255 |

**Coste del turno (USD) y múltiplo respecto al turno 1** (media de las sesiones que llegaron a ese turno).

| escenario | T1 | T3 | T6 | T10 | T20 (n) | acumulado en T20 |
|---|---|---|---|---|---|---|
| growing | 0.00042 | 0.00052 (1.2x) | 0.00077 (1.8x) | 0.00083 (2.0x) | 0.00113 (2.7x) (2) | 0.0162 |
| pivot | 0.00054 | 0.00221 (4.1x) | 0.00152 (2.8x) | 0.00083 (1.5x) | 0.00234 (4.4x) (2) | 0.0251 |
| contradiction | 0.00043 | 0.00169 (4.0x) | 0.00225 (5.3x) | 0.00083 (2.0x) | 0.00119 (2.8x) (1) | 0.0258 |

**Recall de facts (`MemoryDriftMetric`) vs N.** Solo se evalúan facts que ya salieron de la ventana (el del turno *k* sale al cerrarse el turno *k*+6); en N = 1, 3 y 6 no hay ninguno y el recall sería trivial.

| escenario | N = 10 | N = 20 |
|---|---|---|
| growing | 1.00 (3/3) | 1.00 (8/8) |
| pivot | 1.00 (6/6) | 1.00 (6/6) |
| contradiction | 0.83 (5/6) | 0.67 (2/3) |

**Adjuntos** (PDF sintético, un turno, mismo transcript corto).

| adjunto | chars llegados | tokens_in medio | P50 ms | coste medio USD |
|---|---|---|---|---|
| 0 | 0 | 2,951 | 4,115 | 0.00054 |
| 5 KB | 5,134 | 4,633 | 4,096 | 0.00090 |
| 20 KB | 20,108 | 11,034 | 4,469 | 0.00185 |
| 50 KB | 50,062 | 28,180 | 5,011 | 0.00444 |
| 100 KB | 60,062 (de 100,041) | 28,237 | 5,603 | 0.00441 |

## 3. Dónde empieza a romperse mi CAG y por qué

En 20 turnos el CAG no falla de forma visible (5 errores en 195 turnos, 2,6 %, ya tras reintentos), pero degrada por dos vías desde muy pronto. La **latencia** incumple el SLA de 4 s a partir del turno 3: el turno 1 lo cumple en 9 de 9 sesiones (P50 2,5 s), el turno 3 en 1 de 9, el 10 en 0 de 9 y el 20 en 0 de 5 (P50 5,7 s y 10,1 s); en conjunto solo 23 de 190 turnos están dentro. La causa no es el tamaño del contexto sino la longitud de la respuesta: con 230 tokens de salida la mediana es 3,1 s y con 2.304 es 22,9 s, mientras que con más de 20.000 tokens de entrada (los adjuntos) es 5,3 s. La **memoria** se rompe en silencio y de forma selectiva. Lo que vive en `ProjectMetadata` (nombre, tecnologías) sobrevive: recall 0,99 en `growing` y 1,00 en `pivot`. Lo que solo puede vivir en el resumen se pierde. `anchors_count` fue 0 en todos los turnos, porque el presupuesto, redactado de forma natural, no encaja en la regex, así que el 30000 de `contradiction` depende solo del resumen y desaparece en las 3 sesiones, desde el turno 9 (el mismo en que sale de la ventana), 13 y 14. El 80000 desaparece en 1 de 3 sesiones, desde el turno 14, otra vez nada más salir de la ventana. El recall de `contradiction` baja de 0,83 en N = 10 a 0,67 en N = 20, y en tres ejecuciones del mismo experimento osciló entre 0,46 y 0,68 (cifras con pocas comprobaciones: 6 y 3 en estos checkpoints). Ningún test falla ni se devuelve error HTTP: es justo la degradación silenciosa que ninguna métrica anterior detectaba.

La dimensión que más pesa es la **pérdida de memoria**, por invisible, y detrás la **latencia**; el **coste** está sano: queda acotado por la ventana (el turno 10 cuesta entre 1,5 y 2,0 veces el turno 1; el 20, 2,7 veces en `growing` y 4,4 en `pivot`, con n = 2) y los 195 turnos costaron 0,23 USD, todos dentro del presupuesto de 0,01 USD por turno. El caso límite que justifica saltar a RAG está en los **adjuntos**. El tope `MAX_ATTACHMENT_CHARS = 60.000` recorta sin avisar: un PDF de 100 KB (100.041 caracteres) llega con 60.062, es decir, **se pierde el 40 % del documento**, y no hay ninguna señal en la respuesta. Lo que llega se paga además dos veces por turno: el extractor de metadata recibe el mismo texto que el estimador, de modo que el adjunto de 100 KB supone unos 28.200 tokens de entrada frente a ~2.950 sin adjunto, unas 8 veces más de coste (0,0044 frente a 0,00054 USD) que se estabiliza entre 50 y 100 KB solo porque el tope ya actúa. Dos situaciones concretas pasan del límite del CAG: un documento por encima del tope, y cualquier dato que deba sobrevivir más allá de la ventana (como un presupuesto) sin depender de que un resumen lo conserve. Recuperar por relevancia en lugar de meter todo en el prompt resuelve ambas.

## 4. Decisiones de diseño

- **Un evento `turn_observed` por turno** (13 campos + `llm_calls` y `unpriced_calls`). El consumo suma las 2-3 llamadas del turno (estimación, metadata, resumen) con un `MeteredLLM` por turno, sin cambiar las firmas de los servicios auxiliares.
- **El runner lee el estado de la memoria vía `GET /sessions/{id}`** (opción B), no parseando logs de Docker: funciona igual con `--http` y con TestClient. El texto del resumen y de las anclas, que puede contener datos del cliente, solo se expone con `EXPOSE_SESSION_DEBUG=true` (apagado por defecto); `last_turn` solo lleva ids y contadores.
- **Las métricas viven en `evals/stress/metrics.py`**, no en `evals/metrics.py`: el repo no tenía framework de evals que extender y las métricas dependen del shape de `turn_observed` y del snapshot, no de un `EstimationResult`. `MemoryDriftMetric` lanza error si el snapshot no trae `memory`, en vez de dar 0, y solo busca en campos de texto de la metadata.
- **Una conversación de 20 turnos con fotos en N ∈ {1, 3, 6, 10, 20}**, en lugar de cinco conversaciones (20 turnos por repetición en vez de 40).
- **Matriz reducida:** los escenarios multi-turno corren sin adjunto y los tamaños de adjunto se aplican a un escenario de un turno; cruzar ambos ejes habría sido ~900 turnos. Los PDF se calibran en caracteres extraídos, no en bytes (el de «100 KB» pesa 26 KB en disco).
- **Reintento ante 5xx** (hasta 3): un 502 por validación del esquema (los totales no cuadran con las fases) haría perder el turno y, con él, sus facts. Los facts de turnos que fallaron definitivamente no se evalúan.
- **Nada del sistema se optimizó** durante la medición.

## 5. Limitaciones

- **Tokens y coste subestiman los reintentos de validación:** `raw.usage` es solo de la última llamada, mientras que `latency_ms` sí incluye el tiempo de todos los intentos. 24 de 195 turnos (12,3 %) necesitaron reintento.
- **Match exacto:** una paráfrasis («30.000 €») cuenta como olvido. Los canarios de los adjuntos miden lo que el modelo decide mencionar, no lo que recibe, y no se interpretan.
- **N pequeño:** en N = 20 hay 1 sesión de `contradiction` y 2 de `pivot`; los cocientes de coste de T20 salen de 1-2 sesiones. Hay variación entre ejecuciones (recall de `contradiction`: 0,68, 0,46 y 0,67 en tres runs).
- **Fiabilidad:** el mismo experimento falló en el 14,4 % de los turnos sin reintentos, en el 9,7 % con 1 reintento y en el 2,6 % con hasta 3 (los fallos son de validación del esquema y están correlacionados: el segundo intento solo salvó el 59 %). Los datos de este informe son del run con 3 reintentos.
- **El anclaje no se midió:** ningún turno activó la regex de anclas (por diseño); no se evalúa cómo se comporta con un lenguaje que sí la dispare.
- **Camino ACB** no instrumentado; `cache_hit_kind` es siempre `none`.
