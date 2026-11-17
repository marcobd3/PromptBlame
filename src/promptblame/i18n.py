"""Textos de la interfaz en inglés (por defecto) y español."""

from __future__ import annotations

from collections.abc import Callable

from .attribution import DEFAULT_LANGUAGE

LANGUAGE_LABELS = {"en": "English", "es": "Español"}


def detect_language(locale: str | None) -> str:
    """Idioma de la interfaz a partir del locale del navegador ("es-ES" → "es")."""
    code = (locale or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGE_LABELS else DEFAULT_LANGUAGE


EXAMPLES = {
    "en": {
        "system": """You are the support assistant for an online bicycle shop.
Always reply in English, in a friendly tone.
Keep it short: three paragraphs at most.
If the customer asks about an order, ask for the order number.
Do not promise specific delivery dates.
End every reply by offering further help.""",
        "user": "Hi, I bought an e-bike two weeks ago and it still hasn't arrived. When will I get it?",
    },
    "es": {
        "system": """Eres el asistente de soporte de una tienda online de bicicletas.
Responde siempre en español y con un tono cercano.
Sé breve: tres párrafos como máximo.
Si el cliente pregunta por un pedido, pide el número de pedido.
No prometas plazos de entrega concretos.
Termina cada respuesta ofreciendo más ayuda.""",
        "user": "Hola, compré una bici eléctrica hace dos semanas y todavía no me ha llegado. ¿Cuándo la recibiré?",
    },
}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "tagline": "Which instruction in your prompt produced each part of the response?",
        "language": "Language",
        "settings": "Settings",
        "service": "Service",
        "judge_section": "Attribution and rewriting",
        "credentials": "Credentials",
        "of_service": "(service)",
        "of_judge": "(judge)",
        "provider": "Provider {who}",
        "model": "Model {who}",
        "effort": "Effort {who}",
        "model_help": "Pick one from the list or type the identifier of any other model from the provider.",
        "effort_unsupported": "This provider has no common effort setting; it is ignored.",
        "base_url": "Endpoint base URL",
        "api_key": "{provider} API key",
        "optional": " (optional)",
        "key_on_server": "Set on the server",
        "key_help": "If left empty, the server environment variable is used: {envs}. "
        "The key is only used to call the provider; it is never stored or logged.",
        "or": " or ",
        "ablation": "Verify with ablation",
        "ablation_help": "Regenerates the response without each cited instruction to confirm its effect. "
        "Makes one extra call per instruction (plus a control call) with the service model.",
        "max_ablation": "Max. instructions to ablate",
        "compatible_label": "OpenAI-compatible (Ollama, OpenRouter, Mistral…)",
        "compatible_short": "compatible endpoint",
        "tab_blame": "1 · Response and attribution",
        "tab_improve": "2 · Improve the system prompt",
        "input": "Input",
        "generate": "Generate response",
        "calling": "Calling {model}…",
        "output": "Service output",
        "response": "Response",
        "response_help": "You can also paste a response you already have.",
        "attribution": "Attribution",
        "criteria": "Attribution instructions (optional)",
        "criteria_placeholder": """E.g.:
- Tone and language only count as a cause if the response departs from the usual.
- Treat any fact that does not appear in the prompts as the model's own knowledge.
- Be strict: use "high" confidence only if the instruction literally requires it.""",
        "criteria_help": "Context and criteria for judging attributions: what counts as a cause, "
        "what to ignore, how strict to be with confidence, the service's domain… "
        "They are added to the attribution judge's prompt.",
        "criteria_in_rewrite": "Also apply them when generating the new system prompt (tab 2)",
        "criteria_in_rewrite_help": "The tab 2 rewriter receives the same criteria.",
        "view_attribution": "View attribution",
        "need_response": "Generate or paste a response to see which instruction each block comes from.",
        "dialog_title": "Attribution by block",
        "dialog_caption": "Hover over a block to see its quote; click to jump to it. Grey = no source instruction.",
        "attributing": "Attributing each block of the response…",
        "ablating": "Verifying by ablation (regenerating without each instruction)…",
        "need_response_tab2": "First generate (or paste) a response in tab 1.",
        "last_response": "Last response",
        "improvement": "What do you want to improve?",
        "improvement_placeholder": "E.g.: don't ask for the order number if the customer already gave it, "
        "and be shorter.",
        "generate_rewrite": "Generate new system prompt version",
        "rewriting": "Rewriting the system prompt with the attribution map…",
        "rewrite_done": "New version generated.",
        "changes": "Changes",
        "col_target": "Instruction",
        "col_action": "Action",
        "col_change": "Change",
        "col_reason": "Reason",
        "action_modificada": "modified",
        "action_eliminada": "removed",
        "action_nueva": "new",
        "new_version": "New version",
        "diff": "Differences",
        "no_changes": "(no changes)",
        "adopt": "Use this version in tab 1",
        "adopt_help": "Replaces the system prompt; then generate the response again to compare.",
        "previous_versions": "Previous versions ({n})",
    },
    "es": {
        "tagline": "¿Qué instrucción de tu prompt produjo cada parte de la respuesta?",
        "language": "Idioma",
        "settings": "Configuración",
        "service": "Servicio",
        "judge_section": "Atribución y reescritura",
        "credentials": "Credenciales",
        "of_service": "del servicio",
        "of_judge": "del juez",
        "provider": "Proveedor {who}",
        "model": "Modelo {who}",
        "effort": "Esfuerzo {who}",
        "model_help": "Elige uno de la lista o escribe el identificador de cualquier otro modelo del proveedor.",
        "effort_unsupported": "Este proveedor no tiene un ajuste de esfuerzo común; se ignora.",
        "base_url": "URL base del endpoint",
        "api_key": "API key de {provider}",
        "optional": " (opcional)",
        "key_on_server": "Configurada en el servidor",
        "key_help": "Si la dejas vacía se usa la variable de entorno del servidor: {envs}. "
        "La key sólo se usa para llamar al proveedor; no se guarda ni se registra.",
        "or": " o ",
        "ablation": "Verificar con ablación",
        "ablation_help": "Regenera la respuesta quitando cada instrucción citada para confirmar su efecto. "
        "Hace una llamada extra por instrucción (más una de control) con el modelo del servicio.",
        "max_ablation": "Máx. instrucciones a ablacionar",
        "compatible_label": "Compatible con OpenAI (Ollama, OpenRouter, Mistral…)",
        "compatible_short": "endpoint compatible",
        "tab_blame": "1 · Respuesta y atribución",
        "tab_improve": "2 · Mejorar el system prompt",
        "input": "Entrada",
        "generate": "Generar respuesta",
        "calling": "Llamando a {model}…",
        "output": "Salida del servicio",
        "response": "Respuesta",
        "response_help": "También puedes pegar aquí una respuesta que ya tengas.",
        "attribution": "Atribución",
        "criteria": "Instrucciones de atribución (opcional)",
        "criteria_placeholder": """Ej.:
- El tono y el idioma sólo cuentan como causa si la respuesta se aparta de lo habitual.
- Considera conocimiento del modelo cualquier dato que no aparezca en los prompts.
- Sé estricto: usa confianza "alta" sólo si la instrucción lo exige literalmente.""",
        "criteria_help": "Contexto y criterios sobre cómo evaluar las atribuciones: qué cuenta como causa, "
        "qué ignorar, cómo de estricto ser con la confianza, el dominio del servicio… "
        "Se añaden al prompt del juez de atribución.",
        "criteria_in_rewrite": "Aplicarlas también al generar la nueva versión del system prompt (pestaña 2)",
        "criteria_in_rewrite_help": "El reescritor de la pestaña 2 recibe los mismos criterios.",
        "view_attribution": "Ver atribución",
        "need_response": "Genera o pega una respuesta para ver de qué instrucción viene cada bloque.",
        "dialog_title": "Atribución por bloques",
        "dialog_caption": "Pasa el ratón por un bloque para ver su cita; haz clic para saltar a ella. "
        "Gris = sin instrucción de origen.",
        "attributing": "Atribuyendo cada bloque de la respuesta…",
        "ablating": "Verificando por ablación (regenerando sin cada instrucción)…",
        "need_response_tab2": "Primero genera (o pega) una respuesta en la pestaña 1.",
        "last_response": "Última respuesta",
        "improvement": "¿Qué quieres mejorar?",
        "improvement_placeholder": "Ej.: que no pida el número de pedido si el cliente ya lo ha dado, "
        "y que sea más breve.",
        "generate_rewrite": "Generar nueva versión del system prompt",
        "rewriting": "Reescribiendo el system prompt con el mapa de atribución…",
        "rewrite_done": "Nueva versión generada.",
        "changes": "Cambios",
        "col_target": "Instrucción",
        "col_action": "Acción",
        "col_change": "Cambio",
        "col_reason": "Motivo",
        "action_modificada": "modificada",
        "action_eliminada": "eliminada",
        "action_nueva": "nueva",
        "new_version": "Nueva versión",
        "diff": "Diferencias",
        "no_changes": "(sin cambios)",
        "adopt": "Usar esta versión en la pestaña 1",
        "adopt_help": "Sustituye el system prompt; luego vuelve a generar la respuesta para comparar.",
        "previous_versions": "Versiones anteriores ({n})",
    },
}


def translator(language: str) -> Callable[..., str]:
    """Devuelve ``t(key, **kwargs)`` para ``language`` (inglés si no existe)."""
    table = STRINGS.get(language, STRINGS[DEFAULT_LANGUAGE])

    def t(key: str, **kwargs: object) -> str:
        text = table.get(key) or STRINGS[DEFAULT_LANGUAGE][key]
        return text.format(**kwargs) if kwargs else text

    return t
