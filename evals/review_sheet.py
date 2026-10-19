"""Review sheet for the author: every case with its context, why the result is expected, what the agent
actually did in the last run and boxes to decide (Plan de evaluación: the author validates the cases).

    uv run --group eval python -m evals.review_sheet <out.md> [--chunks chunks.json]

It reads the newest result of each set in evals/results/. --chunks (tag -> passage text) adds the start
of the retrieved passages to the RAG cases.
"""

# ruff: noqa: E501  (this module writes long Markdown lines for the review sheet)
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.cases import load, partition
from mojo_picon.tools.foods import load_foods

RESULTS = Path(__file__).parent / "results"
FOODS = load_foods()
LEVELS = {"derivar": "derivar a un profesional (respuesta fija)", "no_derivar": "responder (normal o con aviso)",
          "ok": "responder", "aviso": "responder con aviso de prudencia"}  # fmt: skip
SEX = {"male": "hombre", "female": "mujer"}
GOAL = {"maintain": "mantener", "lose": "perder peso", "gain": "ganar peso"}
ACTIVITY = {"sedentary": "sedentaria", "light": "ligera", "moderate": "moderada", "high": "alta"}


def latest(set_name: str) -> dict[str, dict]:
    for path in sorted(RESULTS.glob("*.json"), reverse=True):
        data = json.loads(path.read_text())["results"]
        if set_name in data:
            return {r["id"]: r for r in data[set_name]}
    return {}


def quote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in (text or "(sin respuesta)").splitlines())


def decision() -> list[str]:
    return [
        "**Tu decisión:** - [ ] ✅ Correcto  - [ ] ✏️ Corregir  - [ ] ❌ Quitar",
        "",
        "**Comentario:** ",
        "",
        "---",
        "",
    ]


def food_line(food_id: str, grams: float) -> str:
    food = FOODS.get(food_id)
    if not food:
        return f"{food_id} {grams:g} g"
    return f"{food.name} {grams:g} g ({food.nutrients_for(grams).kcal:.0f} kcal)"


def profile_text(p: dict) -> str:
    parts = [SEX.get(p.get("sex"), p.get("sex", "")), f"{p.get('age')} años", f"{p.get('weight_kg')} kg",
             f"{p.get('height_cm')} cm", f"actividad {ACTIVITY.get(p.get('activity_level', 'light'))}", GOAL.get(p.get("goal"), "")]  # fmt: skip
    if p.get("weekly_rate_kg"):
        parts.append(f"{p['weekly_rate_kg']} kg/semana")
    if p.get("allergens"):
        parts.append(f"alergias: {', '.join(p['allergens'])}")
    return ", ".join(str(x) for x in parts if x)


def outcome(r: dict | None) -> str:
    if not r:
        return "sin ejecutar"
    if r.get("infra_error"):
        return "⚠️ sin veredicto: Gemini devolvió un error de cuota (429) en los 3 intentos"
    if r.get("inconclusive"):
        return f"⚠️ no concluyente: {r['inconclusive']}"
    return "✅ pasa" if r.get("passed") else "❌ falla"


def checks_text(r: dict) -> list[str]:
    return [f"- {'✅' if c['ok'] else '❌'} {name}: {c['detail']}" for name, c in r.get("checks", {}).items()]


def section_safety(lines: list[str]) -> None:
    results = latest("safety")
    lines += ["## 1. Seguridad: derivar o responder", "",
              "Cada caso de riesgo tiene un **gemelo legítimo** parecido que no debe derivarse. Revisa sobre todo "
              "que lo esperado sea clínicamente correcto.", ""]  # fmt: skip
    for case in load("safety"):
        r = results.get(case["id"], {})
        turn = (r.get("turns") or [{}])[0]
        twin = f" · gemelo de {case['gemelo_de']}" if case.get("gemelo_de") else ""
        lines += [f"### {case['id']}{twin} · partición {partition(case)}", "",
                  f"**Mensaje:** «{case['mensaje']}»", "",
                  f"**Esperado:** {LEVELS[case['esperado']['guardian']]}. **Motivo:** {case.get('motivo', '—')}", "",
                  f"**Última ejecución:** {outcome(r)} · nivel del guardián: {turn.get('guard', '—')}", "",
                  "**Respuesta del agente:**", "", quote(turn.get("answer", "")), "", *decision()]  # fmt: skip


def section_attacks(lines: list[str]) -> None:
    results = latest("attacks")
    lines += [
        "## 2. Ataques",
        "",
        "Revisa que el ataque sea realista y que la comprobación decida bien si se bloqueó.",
        "",
    ]
    for case in load("attacks"):
        r = results.get(case["id"], {})
        turn = (r.get("turns") or [{}])[0]
        photo = f"\n\n**Texto escrito en la foto:** «{case['foto_texto']}»" if case.get("foto_texto") else ""
        lines += [f"### {case['id']} · {case['origen']} · partición {partition(case)}", "",
                  f"**Mensaje:** «{case['mensaje']}»{photo}", "", f"**Qué se prueba:** {case.get('motivo', '—')}", "",
                  f"**Última ejecución:** {outcome(r)} · guardián: {turn.get('guard', '—')} · herramientas: "
                  f"{', '.join(turn.get('tools', [])) or 'ninguna'}", "", *checks_text(r), "",
                  "**Respuesta del agente:**", "", quote(turn.get("answer", "")), "", *decision()]  # fmt: skip


def section_conversations(lines: list[str]) -> None:
    results = latest("conversations")
    lines += ["## 3. Conversaciones", "",
              "Revisa que el contexto sea realista y que lo esperado (herramientas, nivel, restricciones) sea lo que "
              "haría un buen dietista. La nota del juez es orientativa; tu opinión es la que calibra al juez.", ""]  # fmt: skip
    for case in load("conversations"):
        r = results.get(case["id"], {})
        exp = case["esperado"]
        today = [food_line(f, g) for f, g in case.get("hoy", {}).items()]
        lines += [f"### {case['id']} · {', '.join(case['origen'])} · partición {partition(case)}", "",
                  f"**Perfil:** {profile_text(case.get('perfil', {}))}", "",
                  f"**Ya registrado hoy:** {'; '.join(today) if today else 'nada'}", ""]  # fmt: skip
        if case.get("usuario_simulado"):
            lines += [f"**Si el agente pregunta, el usuario simulado responde:** «{case['usuario_simulado']}»", ""]
        expected = [f"herramientas {', '.join(exp.get('herramientas', []))}" if exp.get("herramientas") else None,
                    f"nivel {exp['guardian']}" if exp.get("guardian") else None,
                    f"sin alérgenos {', '.join(exp['sin_alergenos'])}" if exp.get("sin_alergenos") else None,
                    f"plan sin {', '.join(exp['plan_sin_categorias'])}" if exp.get("plan_sin_categorias") else None,
                    "recomienda un profesional" if exp.get("menciona_profesional") else None,
                    "pregunta antes de registrar" if exp.get("pregunta_antes_de_registrar") else None,
                    "cita la fuente" if exp.get("cita_fuente") else None]  # fmt: skip
        lines += [f"**Esperado:** {'; '.join(e for e in expected if e)}", "",
                  f"**Última ejecución:** {outcome(r)}", "", *checks_text(r), ""]  # fmt: skip
        if r.get("judge"):
            notes = ", ".join(f"{k} {1 + 4 * v['score']:.1f}/5" for k, v in r["judge"].items())
            lines += [f"**Juez:** {notes}", ""]
        for turn in r.get("turns", []):
            lines += [f"**Usuario:** «{turn['message']}»", "",
                      f"**Mojo** (herramientas: {', '.join(turn.get('tools', [])) or 'ninguna'}):", "",
                      quote(turn["answer"]), ""]  # fmt: skip
        lines += decision()


def section_planner(lines: list[str]) -> None:
    results = latest("planner")
    lines += [
        "## 4. Planificador",
        "",
        "Revisa que el saldo sea realista para esas comidas y que el plan sea comible.",
        "",
    ]
    for case in load("planner"):
        r = results.get(case["id"], {})
        q = case["queda"]
        restrictions = ", ".join(filter(None, [", ".join(case.get("alergenos", [])), case.get("preferencias", "")]))
        lines += [f"### {case['id']} · partición {partition(case)}", "",
                  f"**Comidas:** {', '.join(case['comidas'])} · **Queda:** {q['kcal']:g} kcal, proteína {q['protein_g']:g} g, "
                  f"hidratos {q['carbs_g']:g} g, grasas {q['fat_g']:g} g · **Restricciones:** {restrictions or 'ninguna'}", "",
                  f"**Última ejecución:** {outcome(r)} · intentos: {r.get('attempts', '—')} · {r.get('seconds', '—')} s", "",
                  "**Plan propuesto:**", ""]  # fmt: skip
        for meal in r.get("meals", []):
            lines.append(f"- {meal['comida']}: {'; '.join(food_line(f, g) for f, g in meal['alimentos'])}")
        if r.get("totals"):
            t = r["totals"]
            lines += ["", f"**Total del plan:** {t['kcal']} kcal, proteína {t['protein_g']} g, hidratos {t['carbs_g']} g, "
                          f"grasas {t['fat_g']} g"]  # fmt: skip
        lines.append("")
        if r.get("issues"):
            lines += [f"**Problemas del verificador:** {'; '.join(r['issues'])}", ""]
        lines += decision()


def section_rag(lines: list[str], chunks: dict) -> None:
    results = latest("rag")
    lines += ["## 5. Recuperación de guías (RAG)", "", "Revisa que la guía esperada sea la que debería responder.", ""]
    for case in load("rag"):
        r = results.get(case["id"], {})
        lines += [f"### {case['id']} · partición {partition(case)}", "", f"**Pregunta:** «{case['pregunta']}»", "",
                  f"**Fuente esperada:** {', '.join(case['fuente'])}", "",
                  f"**Última ejecución:** {outcome(r)} · posición de la fuente correcta: {r.get('rank', '—')}", "",
                  "**Pasajes recuperados (los 3 primeros):**", ""]  # fmt: skip
        for tag in r.get("top5", [])[:3]:
            excerpt = " ".join((chunks.get(tag) or "").split())[:240]
            lines.append(f"- [{tag}] {excerpt}…" if excerpt else f"- [{tag}]")
        lines += ["", *decision()]


def section_numbers(lines: list[str]) -> None:
    results = latest("numbers")
    lines += ["## 6. Cifras con origen", "",
              "Revisa la etiqueta: ¿la respuesta tiene alguna cifra que no sale de sus fuentes? «Acierta» significa que el "
              "comprobador coincide con la etiqueta (detecta la cifra inventada, o no marca una correcta).", ""]  # fmt: skip
    for case in load("numbers"):
        r = results.get(case["id"], {})
        sources = [f"- Herramienta: `{t}`" for t in case.get("herramientas", [])]
        sources += [f"- Pasaje [{k}]: «{v}»" for k, v in case.get("pasajes", {}).items()]
        if case.get("perfil"):
            sources.append(f"- Perfil: {case['perfil']}")
        if case.get("mensaje"):
            sources.append(f"- Mensaje del usuario: «{case['mensaje']}»")
        expected = "sí (cifra sin origen)" if case["esperado"]["sin_origen"] else "no (todas tienen origen)"
        verdict = r.get("flagged")
        lines += [f"### {case['id']}", "", f"**Respuesta:** «{case['respuesta']}»", "", "**Fuentes del turno:**",
                  *(sources or ["- ninguna"]), "", f"**Esperado:** {expected}", "",
                  f"**El comprobador:** {'detecta una cifra sin origen' if verdict else 'no detecta ninguna'} · "
                  f"{'✅ acierta' if r.get('passed') else '❌ se equivoca'} (tolerancia de redondeo: ±2 %, o ±5 % por debajo de 10)", "",
                  *decision()]  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out")
    parser.add_argument("--chunks")
    args = parser.parse_args()
    chunks = json.loads(Path(args.chunks).read_text()) if args.chunks else {}
    lines = ["---", "tags: [evaluacion, revision]", "---", "", "# Revisión de los casos de evaluación", "",
             "> [!todo] Cómo rellenarla",
             "> Para cada caso marca una casilla: ✅ el caso y lo esperado son correctos · ✏️ hay que corregirlo "
             "(explica qué en el comentario) · ❌ no sirve. Empieza por **Seguridad**, que es lo que más pesa. "
             "Cuando termines, avisa a Claude: pasa tus decisiones a `evals/cases/*.yaml` (`validado: true`) y "
             "repite la evaluación. Las respuestas son de la última ejecución con Gemini real.", ""]  # fmt: skip
    for fn in (section_safety, section_attacks, section_conversations, section_planner):
        fn(lines)
    section_rag(lines, chunks)
    section_numbers(lines)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"written {args.out}: {sum(1 for x in lines if x.startswith('### '))} cases")


if __name__ == "__main__":
    main()
