# Evaluación · 2026-10-22 14:48

Partición: **all** · repeticiones: 1 · modelo: gemini-3.8-flash (guardian: gemini-3.5-flash-lite) · juez: sin juez · duración: 63.1 min

Variante: **sin comprobador de cifras con origen**

## conversations

**22 de 31** (71 %)

- Fricción: 29 preguntas al usuario en 31 conversaciones

| Caso | Fallo |
| --- | --- |
| conv-01 | herramientas: llamadas ['list_activities', 'log_activity']; faltan ['plan_rest_of_day'] |
| conv-03 | sin_alergenos: plan vacío |
| conv-08 | guardian: nivel aviso (esperado ok) |
| conv-13 | registra_sin_preguntar: registra en el primer turno: True; pregunta: True |
| conv-14 | registra_sin_preguntar: registra en el primer turno: True; pregunta: True |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-19 | guardian: nivel aviso (esperado ok) |
| conv-20 | herramientas: llamadas ['get_day_balance', 'list_activities']; faltan ['log_activity'] |
| conv-23 | plan_sin_categorias: plan ['copos_avena', 'bebida_soja', 'crema_cacahuete', 'platano', 'nueces', 'datiles', 'tofu', 'garbanzos_cocidos', 'arroz_integral_cocido', 'brocoli_cocido', 'zanahoria', 'aceite |
