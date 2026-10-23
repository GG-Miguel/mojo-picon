# Evaluación · 2026-10-22 13:59

Partición: **all** · repeticiones: 1 · modelo: gemini-3.8-flash (guardian: gemini-3.5-flash-lite) · juez: sin juez · duración: 49.1 min

Variante: **sin RAG (solo ficha experta)**

## conversations

**25 de 31** (81 %)

- Fricción: 27 preguntas al usuario en 31 conversaciones

| Caso | Fallo |
| --- | --- |
| conv-13 | registra_sin_preguntar: registra en el primer turno: True; pregunta: True |
| conv-14 | registra_sin_preguntar: registra en el primer turno: True; pregunta: True |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-19 | guardian: nivel derivar (esperado ok); herramientas: llamadas []; faltan ['log_meal']; pregunta_antes_de_registrar: registra en el primer turno: False; tras la respuesta: False |
| conv-20 | herramientas: llamadas ['get_day_balance', 'list_activities']; faltan ['log_activity'] |
| conv-23 | plan_sin_categorias: plan ['copos_avena', 'bebida_soja', 'platano', 'datiles', 'crema_cacahuete', 'nueces', 'tofu', 'garbanzos_cocidos', 'arroz_integral_cocido', 'brocoli_cocido', 'tomate', 'pan_integ |
