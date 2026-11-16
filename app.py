"""PromptBlame: interfaz de Streamlit.

Ejecuta con:  streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from promptblame.attribution import Attribution, attribute, verify_by_ablation
from promptblame.llm import EFFORTS, LLM, MODELS, LLMError
from promptblame.render import attribution_html
from promptblame.rewrite import rewrite_system_prompt, unified_diff

st.set_page_config(page_title="PromptBlame", page_icon="🔍", layout="wide")

EXAMPLE_SYSTEM = """Eres el asistente de soporte de una tienda online de bicicletas.
Responde siempre en español y con un tono cercano.
Sé breve: tres párrafos como máximo.
Si el cliente pregunta por un pedido, pide el número de pedido.
No prometas plazos de entrega concretos.
Termina cada respuesta ofreciendo más ayuda."""

EXAMPLE_USER = "Hola, compré una bici eléctrica hace dos semanas y todavía no me ha llegado. ¿Cuándo la recibiré?"

defaults = {
    "system_prompt": EXAMPLE_SYSTEM,
    "user_prompt": EXAMPLE_USER,
    "response": "",
    "attribution": None,
    "show_view": False,
    "rewrite": None,
    "versions": [],
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)


# --- Barra lateral: configuración -------------------------------------------

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input(
        "API key de Anthropic",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Si la dejas vacía se usan las credenciales del entorno.",
    )
    gen_model = st.selectbox("Modelo del servicio", MODELS, index=0)
    gen_effort = st.select_slider("Esfuerzo del servicio", EFFORTS, value="medium")
    st.divider()
    judge_model = st.selectbox("Modelo de atribución y reescritura", MODELS, index=0)
    judge_effort = st.select_slider("Esfuerzo de atribución", EFFORTS, value="high")
    st.divider()
    use_ablation = st.checkbox(
        "Verificar con ablación",
        value=False,
        help="Regenera la respuesta quitando cada instrucción citada para confirmar su efecto. "
        "Hace una llamada extra por instrucción (más una de control).",
    )
    max_ablation = st.number_input("Máx. instrucciones a ablacionar", 1, 30, 8, disabled=not use_ablation)


def make_llm(model: str) -> LLM:
    return LLM(model=model, api_key=api_key or None)


def invalidate_attribution() -> None:
    st.session_state.attribution = None
    st.session_state.show_view = False


def current_attribution_is_fresh() -> bool:
    attr: Attribution | None = st.session_state.attribution
    return attr is not None and (
        attr.system_prompt,
        attr.user_prompt,
        attr.response,
    ) == (st.session_state.system_prompt, st.session_state.user_prompt, st.session_state.response)


def compute_attribution() -> Attribution | None:
    if current_attribution_is_fresh():
        return st.session_state.attribution
    try:
        with st.spinner("Atribuyendo cada bloque de la respuesta…"):
            attr = attribute(
                make_llm(judge_model),
                st.session_state.system_prompt,
                st.session_state.user_prompt,
                st.session_state.response,
                effort=judge_effort,
            )
        if use_ablation and attr.blocks:
            with st.spinner("Verificando por ablación (regenerando sin cada instrucción)…"):
                verify_by_ablation(make_llm(gen_model), attr, effort=gen_effort, max_sources=int(max_ablation))
    except LLMError as exc:
        st.error(str(exc))
        return None
    st.session_state.attribution = attr
    return attr



# --- Interfaz -----------------------------------------------------------------

st.title("🔍 PromptBlame")
st.caption("¿Qué instrucción de tu prompt produjo cada parte de la respuesta?")

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
                    st.session_state.response = make_llm(gen_model).text(
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
            st.session_state.show_view = True

    if st.session_state.show_view and st.session_state.response.strip():
        attr = compute_attribution()
        if attr is not None:
            st.divider()
            st.subheader("Atribución por bloques")
            st.caption(
                "Pasa el ratón por un bloque para ver su cita; haz clic para saltar a ella. "
                "Gris = sin instrucción de origen."
            )
            for note in attr.notes:
                st.info(note)
            components.html(attribution_html(attr), height=720, scrolling=False)

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
                            make_llm(judge_model), attr, improvement, effort=judge_effort
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
