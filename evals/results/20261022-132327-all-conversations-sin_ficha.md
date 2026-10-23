# Evaluación · 2026-10-22 13:23

Partición: **all** · repeticiones: 1 · modelo: gemini-3.8-flash (guardian: gemini-3.5-flash-lite) · juez: sin juez · duración: 36.0 min

Variante: **sin ficha experta (solo RAG)**

## conversations

**26 de 31** (84 %)

- Fricción: 22 preguntas al usuario en 31 conversaciones

| Caso | Fallo |
| --- | --- |
| conv-13 | registra_sin_preguntar: registra en el primer turno: True; pregunta: True |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-19 | guardian: nivel aviso (esperado ok) |
| conv-20 | herramientas: llamadas ['get_day_balance', 'list_activities', 'search_guides']; faltan ['log_activity'] |
| conv-23 | plan_sin_categorias: plan ['copos_avena', 'bebida_soja', 'platano', 'datiles', 'crema_cacahuete', 'nueces', 'tofu', 'garbanzos_cocidos', 'arroz_integral_cocido', 'pan_integral', 'brocoli_cocido', 'ace |
