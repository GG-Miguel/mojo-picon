# Modelos por papel · 2026-10-22 14:33

Cada fila cambia el modelo de un papel; el resto sigue en el de referencia. Los casos con error de infraestructura (p. ej. un 429) o no concluyentes no cuentan en las tasas. Coste en milésimas de dólar (m$) por caso, con los precios de `evals/prices.py` (sin descontar la caché: es un máximo).

## safety

| Configuración | Pasan | Sin veredicto | Riesgos derivados | Bloqueos de más | Coste por caso (m$) | Del papel cambiado (m$) | Desde 2027 (m$) | Tokens por caso | Latencia mediana |
|---|---|---|---|---|---|---|---|---|---|
| referencia (gemini-3.8-flash) | 77/78 | 0 | 38/39 | 0/39 | 11.94 | — | 23.88 | 11.921 | 12.8 s |

## attacks

| Configuración | Pasan | Sin veredicto | Coste por caso (m$) | Del papel cambiado (m$) | Desde 2027 (m$) | Tokens por caso | Latencia mediana |
|---|---|---|---|---|---|---|---|
| referencia (gemini-3.8-flash) | 33/33 | 3 | 3.16 | — | 6.33 | 3.351 | 6.1 s |
| coach: gemini-4-argon | 11/11 | 1 | 9.31 | 8.59 | 18.62 | 3.971 | 5.3 s |

## planner

| Configuración | Pasan | Sin veredicto | Al primer intento | Intentos medios | Coste por caso (m$) | Del papel cambiado (m$) | Desde 2027 (m$) | Tokens por caso | Latencia mediana |
|---|---|---|---|---|---|---|---|---|---|
| referencia (gemini-3.8-flash) | 30/30 | 0 | 24/30 | 1.2 | 15.70 | — | 31.40 | 8.035 | 23.8 s |

## conversations

| Configuración | Pasan | Sin veredicto | adecuacion | seguridad | uso_de_guias | claridad | Coste por caso (m$) | Del papel cambiado (m$) | Desde 2027 (m$) | Tokens por caso | Latencia mediana |
|---|---|---|---|---|---|---|---|---|---|---|---|
| referencia (gemini-3.8-flash) | 39/44 | 1 | 4.6 | 4.9 | 5.0 | 4.7 | 35.45 | — | 70.91 | 31.237 | 25.1 s |
| coach: gemini-3.1-flash-lite | 33/45 | 0 | 4.3 | 4.9 | 5.0 | 4.1 | 14.55 | 7.71 | 21.38 | 30.526 | 34.1 s |
| coach: gemini-3.5-flash-lite | 36/45 | 0 | 4.5 | 4.9 | 5.0 | 4.4 | 18.12 | 10.52 | 25.71 | 34.080 | 21.6 s |
| coach: gemini-4-argon | 10/15 | 0 | 4.5 | 4.7 | 5.0 | 4.3 | 110.22 | 101.86 | 220.45 | 43.385 | 389.8 s |

Ejecuciones:

- referencia (gemini-3.8-flash): `evals/results/20261021-163137-all-safety+attacks+planner+conversations-v4-vertex.json`
- coach: gemini-3.1-flash-lite: `evals/results/20261022-132901-all-conversations-v4-vertex.json`
- coach: gemini-3.5-flash-lite: `evals/results/20261022-131011-all-conversations-v4-vertex.json`
- coach: gemini-4-argon: `evals/results/20261022-115454-all-attacks+conversations-v4-vertex.json`
