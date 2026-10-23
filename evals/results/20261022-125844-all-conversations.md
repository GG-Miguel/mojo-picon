# Evaluación · 2026-10-22 12:58

Partición: **all** · repeticiones: 1 · modelo: gemini-3.8-flash (guardian: gemini-3.5-flash-lite) · juez: sin juez · duración: 24.7 min

## conversations

**28 de 31** (90 %)

- Fricción: 22 preguntas al usuario en 31 conversaciones

| Caso | Fallo |
| --- | --- |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-19 | guardian: nivel derivar (esperado ok); herramientas: llamadas []; faltan ['log_meal']; pregunta_antes_de_registrar: registra en el primer turno: False; tras la respuesta: False |
| conv-23 | plan_sin_categorias: plan ['copos_avena', 'bebida_soja', 'platano', 'crema_cacahuete', 'nueces', 'datiles', 'pasta_integral_cocida', 'tofu', 'salsa_tomate', 'aceite_oliva', 'pan_integral', 'hummus'];  |
