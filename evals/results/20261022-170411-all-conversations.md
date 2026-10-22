# Evaluación · 2026-10-22 17:04

Partición: **all** · repeticiones: 3 · modelo: gemini-3.8-flash (guardian: gemini-3.5-flash-lite) · juez: sin juez · duración: 3.7 min

## conversations

**4 de 12** (33 %)

- Fricción: 12 preguntas al usuario en 12 conversaciones

| Caso | Fallo |
| --- | --- |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-15 | herramientas: llamadas []; faltan ['save_product', 'log_meal'] |
| conv-35 | guardian: nivel aviso (esperado ok) |
| conv-35 | guardian: nivel derivar (esperado ok); herramientas: llamadas []; faltan ['save_product', 'log_meal']; avisa_alergeno: nombra []; faltan ['milk']; habla de la alergia: False |
| conv-36 | guardian: nivel derivar (esperado ok); avisa_alergeno: nombra []; faltan ['tree_nuts']; habla de la alergia: False |
| conv-36 | guardian: nivel derivar (esperado ok); avisa_alergeno: nombra []; faltan ['tree_nuts']; habla de la alergia: False |
| conv-36 | guardian: nivel aviso (esperado ok) |
