"""Fixed answers written beforehand, without an LLM ("a canned answer is sometimes the safest").

Used when the guardian says "derivar", when Gemini blocks a call and when a turn hits a limit.
User-facing text: Spanish.
"""

from __future__ import annotations

_PROFESSIONAL = (
    "Esto lo tiene que valorar un profesional sanitario: habla con tu médico de familia o con un "
    "dietista-nutricionista colegiado. Si es urgente o te encuentras mal, llama al 112."
)

FIXED_RESPONSES = {
    "medication": (
        "No puedo darte pautas de medicación ni de dosis, tampoco de insulina: un error ahí es peligroso. "
        + _PROFESSIONAL
    ),
    "diabetes": (
        "Con diabetes, la alimentación y el ejercicio tienen que ajustarse con tu equipo sanitario, "
        "porque afectan a tu tratamiento. " + _PROFESSIONAL
    ),
    "kidney_disease": "Con una enfermedad renal la dieta forma parte del tratamiento. " + _PROFESSIONAL,
    "fever": (
        "Con fiebre no es buen momento para entrenar ni para ajustar la dieta por tu cuenta. Descansa, "
        "hidrátate y, si la fiebre es alta o dura más de un par de días, consulta a tu médico."
    ),
    "minor": (
        "Mojo Picón está pensado para adultos. Para la alimentación de un menor, lo adecuado es hablarlo "
        "con su pediatra o con un dietista-nutricionista."
    ),
    "pregnancy_clinical": (
        "Durante el embarazo o la lactancia no conviene hacer dietas para perder peso ni ajustar calorías "
        "por tu cuenta. " + _PROFESSIONAL
    ),
    "eating_disorder": (
        "Gracias por contármelo. Lo que describes merece atención de un profesional, y no tienes que "
        "pasarlo sola ni solo: habla con tu médico de familia, que puede orientarte hacia ayuda "
        "especializada. Si en algún momento sientes que corres peligro, llama al 112."
    ),
    "alcohol": (
        "Gracias por contármelo. Lo que describes con el alcohol merece que lo hables con un profesional: "
        "tu médico de familia puede orientarte y no tienes que resolverlo por tu cuenta. "
        "Si en algún momento te encuentras mal o corres peligro, llama al 112."
    ),
    "extreme_goal": (
        "Perder peso tan rápido no es seguro y suele recuperarse después. Puedo ayudarte con un objetivo "
        "moderado, de hasta 1 kg por semana; si necesitas algo más rápido por un motivo de salud, "
        "consúltalo con un profesional."
    ),
    "diagnosis": "No puedo hacer diagnósticos. " + _PROFESSIONAL,
    "jailbreak": (
        "No puedo saltarme mis normas: están para que las recomendaciones sean seguras. Si quieres, "
        "te ayudo con tu alimentación o tu entrenamiento de hoy."
    ),
    "off_topic": (
        "Solo puedo ayudarte con alimentación, actividad física y tu diario de comidas. ¿Te ayudo con algo de eso?"
    ),
}
DEFAULT_REFERRAL = _PROFESSIONAL

SAFETY_BLOCK_RESPONSE = "No puedo responder a eso. Si quieres, te ayudo con tu alimentación o tu actividad de hoy."
STEP_LIMIT_RESPONSE = (
    "No he podido completar la respuesta en el número de pasos permitido. Te digo lo que tengo hasta "
    "ahora y, si quieres, lo intentamos con una pregunta más concreta."
)
WARNING_SENTENCE = (
    "Es una orientación general: por tu situación, si tienes dudas, consúltalo con un profesional sanitario."
)
NO_RELIABLE_FIGURE = "No tengo un dato fiable para darte alguna de las cifras que me pedías."


def fixed_response(category: str) -> str:
    return FIXED_RESPONSES.get(category, DEFAULT_REFERRAL)
