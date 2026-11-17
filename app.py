"""PromptBlame: interfaz de Streamlit.

Ejecuta con:  streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from promptblame.attribution import Attribution, attribute, verify_by_ablation
from promptblame.llm import DEFAULT_BASE_URL, EFFORTS, LLM, PROVIDERS, LLMError
from promptblame.render import attribution_html
from promptblame.rewrite import rewrite_system_prompt, unified_diff

st.set_page_config(page_title="PromptBlame", page_icon="🔍", layout="wide")

EXAMPLE_SYSTEM = """Eres el asistente de soporte de una tienda online de bicicletas.
Responde siempre en español y con un tono cercano.
Sé breve: tres párrafos como máximo.
Si el cliente pregunta por un pedido, pide el número de pedido.
No prometas plazos de entrega concretos.
Termina cada respuesta ofreciendo más ayuda."""

INSTRUCTIONS_PLACEHOLDER = """Ej.:
- El tono y el idioma sólo cuentan como causa si la respuesta se aparta de lo habitual.
- Considera conocimiento del modelo cualquier dato que no aparezca en los prompts.
- Sé estricto: usa confianza "alta" sólo si la instrucción lo exige literalmente."""

EXAMPLE_USER = "Hola, compré una bici eléctrica hace dos semanas y todavía no me ha llegado. ¿Cuándo la recibiré?"

defaults = {
    "system_prompt": EXAMPLE_SYSTEM,
    "user_prompt": EXAMPLE_USER,
    "response": "",
    "attribution": None,
    "rewrite": None,
    "versions": [],
    "judge_instructions": "",
    "instructions_in_rewrite": True,
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)


# --- Barra lateral: configuración -------------------------------------------


def model_picker(role: str, label: str, default_effort: str) -> tuple[str, str, str]:
    """Selector de proveedor, modelo y esfuerzo. Devuelve (proveedor, modelo, esfuerzo)."""
    provider_id = st.selectbox(
        f"Proveedor {label}",
        list(PROVIDERS),
        format_func=lambda p: PROVIDERS[p].label,
        key=f"{role}_provider",
    )
    provider = PROVIDERS[provider_id]
    model = st.selectbox(
        f"Modelo {label}",
        provider.models,
        index=0,
        key=f"{role}_model_{provider_id}",
        accept_new_options=True,
        help="Elige uno de la lista o escribe el identificador de cualquier otro modelo del proveedor.",
    )
    effort = st.select_slider(
        f"Esfuerzo {label}",
        EFFORTS,
        value=default_effort,
        key=f"{role}_effort",
        disabled=not provider.supports_effort,
        help=None if provider.supports_effort else "Este proveedor no tiene un ajuste de esfuerzo común; se ignora.",
    )
    return provider_id, model or "", effort


with st.sidebar:
    st.header("Configuración")
    st.subheader("Servicio")
    gen_provider, gen_model, gen_effort = model_picker("gen", "del servicio", "medium")
    st.divider()
    st.subheader("Atribución y reescritura")
    judge_provider, judge_model, judge_effort = model_picker("judge", "del juez", "high")
    st.divider()

    st.subheader("Credenciales")
    api_keys: dict[str, str] = {}
    base_url = ""
    for provider_id in dict.fromkeys([gen_provider, judge_provider]):
        provider = PROVIDERS[provider_id]
        env_value = next((os.environ[k] for k in provider.env_keys if os.environ.get(k)), "")
        if provider.needs_base_url:
            base_url = st.text_input(
                "URL base del endpoint",
                value=os.environ.get("OPENAI_COMPATIBLE_BASE_URL", DEFAULT_BASE_URL),
                help="Ollama: http://localhost:11434/v1 · OpenRouter: https://openrouter.ai/api/v1 · "
                "Mistral: https://api.mistral.ai/v1",
            )
        api_keys[provider_id] = st.text_input(
            f"API key de {provider.short or provider.label}" + ("" if provider.key_required else " (opcional)"),
            value=env_value,
            type="password",
            key=f"api_key_{provider_id}",
            help="Si la dejas vacía se usan las variables de entorno: " + ", ".join(provider.env_keys) + ".",
        )
    st.divider()
    use_ablation = st.checkbox(
        "Verificar con ablación",
        value=False,
        help="Regenera la respuesta quitando cada instrucción citada para confirmar su efecto. "
        "Hace una llamada extra por instrucción (más una de control) con el modelo del servicio.",
    )
    max_ablation = st.number_input("Máx. instrucciones a ablacionar", 1, 30, 8, disabled=not use_ablation)


def make_llm(provider_id: str, model: str) -> LLM:
    return LLM(
        model=model,
        provider=provider_id,
        api_key=api_keys.get(provider_id) or None,
        base_url=base_url or None,
    )


def gen_llm() -> LLM:
    return make_llm(gen_provider, gen_model)


def judge_llm() -> LLM:
    return make_llm(judge_provider, judge_model)


def invalidate_attribution() -> None:
    st.session_state.attribution = None


def current_attribution_is_fresh() -> bool:
    attr: Attribution | None = st.session_state.attribution
    return attr is not None and (
        attr.system_prompt,
        attr.user_prompt,
        attr.response,
        attr.instructions,
    ) == (
        st.session_state.system_prompt,
        st.session_state.user_prompt,
        st.session_state.response,
        st.session_state.judge_instructions.strip(),
    )


def compute_attribution() -> Attribution | None:
    if current_attribution_is_fresh():
        return st.session_state.attribution
    try:
        with st.spinner("Atribuyendo cada bloque de la respuesta…"):
            attr = attribute(
                judge_llm(),
                st.session_state.system_prompt,
                st.session_state.user_prompt,
                st.session_state.response,
                effort=judge_effort,
                instructions=st.session_state.judge_instructions,
            )
        if use_ablation and attr.blocks:
            with st.spinner("Verificando por ablación (regenerando sin cada instrucción)…"):
                verify_by_ablation(gen_llm(), attr, effort=gen_effort, max_sources=int(max_ablation))
    except LLMError as exc:
        st.error(str(exc))
        return None
    st.session_state.attribution = attr
    return attr



def theme_type() -> str | None:
    try:
        return st.context.theme.type
    except AttributeError:  # Streamlit sin st.context.theme
        return None


@st.dialog("Atribución por bloques", width=1300)
def show_attribution_dialog() -> None:
    attr = compute_attribution()
    if attr is None:
        return
    st.caption(
        "Pasa el ratón por un bloque para ver su cita; haz clic para saltar a ella. "
        "Gris = sin instrucción de origen."
    )
    for note in attr.notes:
        st.info(note)
    components.html(attribution_html(attr, theme=theme_type()), height=680, scrolling=False)


# --- Interfaz -----------------------------------------------------------------

st.title("🔍 PromptBlame")
st.caption("¿Qué instrucción de tu prompt produjo cada parte de la respuesta?")

with st.expander("Instrucciones personalizadas de evaluación (opcional)", expanded=False):
    st.text_area(
        "Criterios para el juez",
        key="judge_instructions",
        height=130,
        placeholder=INSTRUCTIONS_PLACEHOLDER,
        on_change=invalidate_attribution,
        help="Contexto y criterios sobre cómo evaluar las atribuciones: qué cuenta como causa, "
        "qué ignorar, cómo de estricto ser con la confianza, el dominio del servicio… "
        "Se añaden al prompt del juez de atribución.",
    )
    st.checkbox(
        "Aplicarlas también al generar la nueva versión del system prompt",
        key="instructions_in_rewrite",
        help="El reescritor de la pestaña 2 recibe los mismos criterios.",
    )

tab_blame, tab_improve = st.tabs(["1 · Respuesta y atribución", "2 · Mejorar el system prompt"])

with tab_blame:
    col_in, col_out = st.columns(2)
    with col_in:
        st.subheader("Entrada")
        st.text_area("System prompt", key="system_prompt", height=220, on_change=invalidate_attribution)
        st.text_area("User prompt", key="user_prompt", height=120, on_change=invalidate_attribution)
        if st.button("Generar respuesta", type="primary"):
            try:
                with st.spinner(f"Llamando a {gen_model}…"):
                    st.session_state.response = gen_llm().text(
                        st.session_state.system_prompt, st.session_state.user_prompt, effort=gen_effort
                    )
                invalidate_attribution()
                st.rerun()
            except LLMError as exc:
                st.error(str(exc))
    with col_out:
        st.subheader("Salida del servicio")
        st.text_area(
            "Respuesta",
            key="response",
            height=388,
            on_change=invalidate_attribution,
            help="También puedes pegar aquí una respuesta que ya tengas.",
        )
        if st.button("Ver atribución", disabled=not st.session_state.response.strip()):
            show_attribution_dialog()

with tab_improve:
    if not st.session_state.response.strip():
        st.info("Primero genera (o pega) una respuesta en la pestaña 1.")
    else:
        with st.expander("Última respuesta", expanded=False):
            st.markdown(st.session_state.response)
        improvement = st.text_area(
            "¿Qué quieres mejorar?",
            placeholder="Ej.: que no pida el número de pedido si el cliente ya lo ha dado, y que sea más breve.",
            height=110,
        )
        if st.button("Generar nueva versión del system prompt", type="primary", disabled=not improvement.strip()):
            attr = compute_attribution()
            if attr is not None:
                try:
                    with st.spinner("Reescribiendo el system prompt con el mapa de atribución…"):
                        st.session_state.rewrite = rewrite_system_prompt(
                            judge_llm(),
                            attr,
                            improvement,
                            effort=judge_effort,
                            instructions=(
                                st.session_state.judge_instructions
                                if st.session_state.instructions_in_rewrite
                                else ""
                            ),
                        )
                except LLMError as exc:
                    st.error(str(exc))

        result = st.session_state.rewrite
        if result is not None:
            st.success(result.summary or "Nueva versión generada.")
            if result.changes:
                st.markdown("**Cambios**")
                st.dataframe(
                    [
                        {
                            "Instrucción": c.get("target", ""),
                            "Acción": c.get("action", ""),
                            "Cambio": c.get("description", ""),
                            "Motivo": c.get("reason", ""),
                        }
                        for c in result.changes
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            col_new, col_diff = st.columns(2)
            with col_new:
                st.markdown("**Nueva versión**")
                st.code(result.new_system_prompt, language=None, wrap_lines=True)
            with col_diff:
                st.markdown("**Diferencias**")
                st.code(unified_diff(st.session_state.system_prompt, result.new_system_prompt) or "(sin cambios)", language="diff")

            def adopt() -> None:
                st.session_state.versions.append(st.session_state.system_prompt)
                st.session_state.system_prompt = result.new_system_prompt
                st.session_state.response = ""
                st.session_state.rewrite = None
                invalidate_attribution()

            st.button(
                "Usar esta versión en la pestaña 1",
                on_click=adopt,
                help="Sustituye el system prompt; luego vuelve a generar la respuesta para comparar.",
            )

        if st.session_state.versions:
            with st.expander(f"Versiones anteriores ({len(st.session_state.versions)})"):
                for i, version in enumerate(reversed(st.session_state.versions), 1):
                    st.markdown(f"**v-{i}**")
                    st.code(version, language=None, wrap_lines=True)
