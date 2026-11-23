"""PromptBlame: interfaz de Streamlit.

Ejecuta con ``promptblame`` (instalado con ``pip install "promptblame[app]"``) o,
desde una copia del repositorio, con ``streamlit run app.py``.

La interfaz está en inglés por defecto y en español si el navegador lo está
(``st.context.locale``); se puede cambiar en la barra lateral.

Al arrancar carga el ``.env`` del directorio de trabajo (ver ``.env.example``):
las API keys quedan disponibles en el servidor y los proveedores, modelos y
esfuerzos que indique son los valores iniciales de la barra lateral.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from promptblame.attribution import Attribution, attribute, verify_by_ablation
from promptblame.config import RoleSettings, load_env, settings
from promptblame.dead import DeadInstructionReport, scan_dead_instructions, split_user_prompts
from promptblame.i18n import EXAMPLES, LANGUAGE_LABELS, detect_language, translator
from promptblame.llm import EFFORTS, LLM, PROVIDERS, LLMError, env_api_key
from promptblame.render import attribution_html
from promptblame.rewrite import rewrite_system_prompt, unified_diff

# Antes de leer ninguna variable: el .env (si existe) completa el entorno.
load_env()
cfg = settings()

st.set_page_config(page_title="PromptBlame", page_icon="🔍", layout="wide")


def browser_locale() -> str | None:
    try:
        locale: str | None = st.context.locale
    except AttributeError:  # Streamlit sin st.context.locale
        return None
    return locale


if "lang" not in st.session_state:
    st.session_state.lang = cfg.language or detect_language(browser_locale())

defaults: dict[str, object] = {
    "system_prompt": EXAMPLES[st.session_state.lang]["system"],
    "user_prompt": EXAMPLES[st.session_state.lang]["user"],
    "response": "",
    "attribution": None,
    "rewrite": None,
    "versions": [],
    "judge_instructions": "",
    "instructions_in_rewrite": True,
    "dead_prompts": EXAMPLES[st.session_state.lang]["user"],
    "dead_report": None,
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)


def on_language_change() -> None:
    """Si los prompts siguen siendo el ejemplo, se cambian por el del nuevo idioma."""
    new = st.session_state.lang
    for field, example_key in (("system_prompt", "system"), ("user_prompt", "user"), ("dead_prompts", "user")):
        if any(st.session_state[field] == EXAMPLES[lang][example_key] for lang in EXAMPLES):
            st.session_state[field] = EXAMPLES[new][example_key]
    st.session_state.attribution = None
    st.session_state.rewrite = None


# --- Barra lateral: configuración -------------------------------------------

with st.sidebar:
    st.selectbox(
        "🌐 Language / Idioma",
        list(LANGUAGE_LABELS),
        format_func=LANGUAGE_LABELS.__getitem__,
        key="lang",
        on_change=on_language_change,
    )

lang: str = st.session_state.lang
t = translator(lang)


def provider_label(provider_id: str) -> str:
    return t("compatible_label") if provider_id == "compatible" else PROVIDERS[provider_id].label


def provider_short(provider_id: str) -> str:
    if provider_id == "compatible":
        return t("compatible_short")
    provider = PROVIDERS[provider_id]
    return provider.short or provider.label


def model_picker(role: str, who: str, defaults: RoleSettings) -> tuple[str, str, str]:
    """Selector de proveedor, modelo y esfuerzo. Devuelve (proveedor, modelo, esfuerzo).

    Los valores iniciales salen de ``defaults`` (variables de entorno o ``.env``).
    """
    provider_id = st.selectbox(
        t("provider", who=who),
        list(PROVIDERS),
        index=list(PROVIDERS).index(defaults.provider),
        format_func=provider_label,
        key=f"{role}_provider",
    )
    provider = PROVIDERS[provider_id]
    models = list(provider.models)
    if provider_id == defaults.provider and defaults.model not in models:
        models.insert(0, defaults.model)  # modelo del .env que no está en la lista sugerida
    model = st.selectbox(
        t("model", who=who),
        models,
        index=models.index(defaults.model) if provider_id == defaults.provider else 0,
        key=f"{role}_model_{provider_id}",
        accept_new_options=True,
        help=t("model_help"),
    )
    effort = st.select_slider(
        t("effort", who=who),
        EFFORTS,
        value=defaults.effort,
        key=f"{role}_effort",
        disabled=not provider.supports_effort,
        help=None if provider.supports_effort else t("effort_unsupported"),
    )
    return provider_id, model or "", effort


with st.sidebar:
    st.header(t("settings"))
    st.subheader(t("service"))
    gen_provider, gen_model, gen_effort = model_picker("gen", t("of_service"), cfg.service)
    st.divider()
    st.subheader(t("judge_section"))
    judge_provider, judge_model, judge_effort = model_picker("judge", t("of_judge"), cfg.judge)
    st.divider()

    st.subheader(t("credentials"))
    api_keys: dict[str, str] = {}
    base_url = ""
    for provider_id in dict.fromkeys([gen_provider, judge_provider]):
        provider = PROVIDERS[provider_id]
        if provider.needs_base_url:
            base_url = st.text_input(
                t("base_url"),
                value=cfg.base_url,
                help="Ollama: http://localhost:11434/v1 · OpenRouter: https://openrouter.ai/api/v1 · "
                "Mistral: https://api.mistral.ai/v1",
            )
        # La key del entorno nunca se precarga en el campo: el valor de un
        # text_input viaja al navegador, así que cualquiera que abriera la app
        # podría leerla. Si el campo queda vacío, LLM la lee del entorno en el
        # servidor.
        has_env_key = env_api_key(provider_id) is not None
        api_keys[provider_id] = st.text_input(
            t("api_key", provider=provider_short(provider_id)) + ("" if provider.key_required else t("optional")),
            type="password",
            key=f"api_key_{provider_id}",
            placeholder=t("key_on_server") if has_env_key else "",
            help=t("key_help", envs=t("or").join(provider.env_keys)),
        )
    st.divider()
    use_ablation = st.checkbox(t("ablation"), value=cfg.ablation, help=t("ablation_help"))
    max_ablation = st.number_input(t("max_ablation"), 1, 30, cfg.max_ablation)


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
        attr.language,
    ) == (
        st.session_state.system_prompt,
        st.session_state.user_prompt,
        st.session_state.response,
        st.session_state.judge_instructions.strip(),
        lang,
    )


def compute_attribution() -> Attribution | None:
    if current_attribution_is_fresh():
        fresh: Attribution = st.session_state.attribution
        return fresh
    try:
        with st.spinner(t("attributing")):
            attr = attribute(
                judge_llm(),
                st.session_state.system_prompt,
                st.session_state.user_prompt,
                st.session_state.response,
                effort=judge_effort,
                instructions=st.session_state.judge_instructions,
                language=lang,
            )
        if use_ablation and attr.blocks:
            with st.spinner(t("ablating")):
                verify_by_ablation(gen_llm(), attr, effort=gen_effort, max_sources=int(max_ablation))
    except LLMError as exc:
        st.error(str(exc))
        return None
    st.session_state.attribution = attr
    return attr


def action_label(action: str) -> str:
    """Las acciones del reescritor llegan como "modificada", "eliminada" o "nueva"."""
    return t(f"action_{action}") if action in ("modificada", "eliminada", "nueva") else action


def theme_type() -> str | None:
    try:
        theme: str | None = st.context.theme.type
    except AttributeError:  # Streamlit sin st.context.theme
        return None
    return theme


@st.dialog(t("dialog_title"), width=1300)
def show_attribution_dialog() -> None:
    attr = compute_attribution()
    if attr is None:
        return
    st.caption(t("dialog_caption"))
    for note in attr.notes:
        st.info(note)
    if not attr.ablation_done and any(b.sources for b in attr.blocks):
        slot = st.empty()
        if slot.button(t("run_ablation"), help=t("ablation_help")):
            slot.empty()
            try:
                with st.spinner(t("ablating")):
                    verify_by_ablation(gen_llm(), attr, effort=gen_effort, max_sources=int(max_ablation))
            except LLMError as exc:
                st.error(str(exc))
    components.html(attribution_html(attr, theme=theme_type(), language=lang), height=680, scrolling=False)


# --- Interfaz -----------------------------------------------------------------

st.title("🔍 PromptBlame")
st.caption(t("tagline"))

tab_blame, tab_improve, tab_dead = st.tabs([t("tab_blame"), t("tab_improve"), t("tab_dead")])

with tab_blame:
    # Entrada a la izquierda, salida a la derecha y, debajo, la atribución.
    col_in, col_out = st.columns(2, gap="large")
    with col_in:
        st.subheader(t("input"))
        st.text_area("System prompt", key="system_prompt", height=200, on_change=invalidate_attribution)
        st.text_area("User prompt", key="user_prompt", height=100, on_change=invalidate_attribution)
        if st.button(t("generate"), type="primary"):
            try:
                with st.spinner(t("calling", model=gen_model)):
                    st.session_state.response = gen_llm().text(
                        st.session_state.system_prompt, st.session_state.user_prompt, effort=gen_effort
                    )
                invalidate_attribution()
                st.rerun()
            except LLMError as exc:
                st.error(str(exc))
    with col_out:
        st.subheader(t("output"))
        st.text_area(
            t("response"),
            key="response",
            height=368,
            on_change=invalidate_attribution,
            help=t("response_help"),
        )

    st.divider()
    st.subheader(t("attribution"))
    st.text_area(
        t("criteria"),
        key="judge_instructions",
        height=110,
        placeholder=t("criteria_placeholder"),
        on_change=invalidate_attribution,
        help=t("criteria_help"),
    )
    st.checkbox(t("criteria_in_rewrite"), key="instructions_in_rewrite", help=t("criteria_in_rewrite_help"))
    if st.button(t("view_attribution"), type="primary", disabled=not st.session_state.response.strip()):
        show_attribution_dialog()
    if not st.session_state.response.strip():
        st.caption(t("need_response"))

with tab_improve:
    if not st.session_state.response.strip():
        st.info(t("need_response_tab2"))
    else:
        with st.expander(t("last_response"), expanded=False):
            # Como texto y no como Markdown: la respuesta del modelo no es de
            # confianza y una imagen Markdown (![](https://…?datos)) haría que el
            # navegador enviara datos a un servidor externo.
            st.code(st.session_state.response, language=None, wrap_lines=True)
        improvement = st.text_area(t("improvement"), placeholder=t("improvement_placeholder"), height=110)
        if st.button(t("generate_rewrite"), type="primary", disabled=not improvement.strip()):
            attr = compute_attribution()
            if attr is not None:
                try:
                    with st.spinner(t("rewriting")):
                        st.session_state.rewrite = rewrite_system_prompt(
                            judge_llm(),
                            attr,
                            improvement,
                            effort=judge_effort,
                            instructions=(
                                st.session_state.judge_instructions if st.session_state.instructions_in_rewrite else ""
                            ),
                            language=lang,
                        )
                except LLMError as exc:
                    st.error(str(exc))

        result = st.session_state.rewrite
        if result is not None:
            st.success(result.summary or t("rewrite_done"))
            if result.changes:
                st.markdown(f"**{t('changes')}**")
                st.dataframe(
                    [
                        {
                            t("col_target"): c.get("target", ""),
                            t("col_action"): action_label(c.get("action", "")),
                            t("col_change"): c.get("description", ""),
                            t("col_reason"): c.get("reason", ""),
                        }
                        for c in result.changes
                    ],
                    hide_index=True,
                    width="stretch",
                )
            col_new, col_diff = st.columns(2)
            with col_new:
                st.markdown(f"**{t('new_version')}**")
                st.code(result.new_system_prompt, language=None, wrap_lines=True)
            with col_diff:
                st.markdown(f"**{t('diff')}**")
                st.code(
                    unified_diff(st.session_state.system_prompt, result.new_system_prompt, language=lang)
                    or t("no_changes"),
                    language="diff",
                )

            def adopt() -> None:
                st.session_state.versions.append(st.session_state.system_prompt)
                st.session_state.system_prompt = result.new_system_prompt
                st.session_state.response = ""
                st.session_state.rewrite = None
                invalidate_attribution()

            st.button(t("adopt"), on_click=adopt, help=t("adopt_help"))

        if st.session_state.versions:
            with st.expander(t("previous_versions", n=len(st.session_state.versions))):
                for i, version in enumerate(reversed(st.session_state.versions), 1):
                    st.markdown(f"**v-{i}**")
                    st.code(version, language=None, wrap_lines=True)

with tab_dead:
    st.caption(t("dead_intro"))
    st.text_area(t("dead_prompts"), key="dead_prompts", height=160, help=t("dead_prompts_help"))
    col_runs, col_threshold = st.columns(2)
    with col_runs:
        dead_runs = int(st.number_input(t("dead_runs"), 1, 10, 3, help=t("dead_runs_help")))
    with col_threshold:
        dead_threshold = st.slider(t("dead_threshold"), 0, 50, 0, step=5, format="%d%%", help=t("dead_threshold_help"))
    dead_prompts = split_user_prompts(st.session_state.dead_prompts)
    total_runs = len(dead_prompts) * dead_runs
    st.caption(t("dead_cost", runs=total_runs, calls=total_runs * 2))
    if st.button(
        t("dead_run"),
        type="primary",
        disabled=not dead_prompts or not st.session_state.system_prompt.strip(),
    ):
        try:
            with st.spinner(t("dead_running", runs=total_runs)):
                st.session_state.dead_report = scan_dead_instructions(
                    gen_llm(),
                    judge_llm(),
                    st.session_state.system_prompt,
                    dead_prompts,
                    runs_per_prompt=dead_runs,
                    threshold=dead_threshold / 100,
                    service_effort=gen_effort,
                    judge_effort=judge_effort,
                    instructions=st.session_state.judge_instructions,
                    language=lang,
                )
        except (LLMError, ValueError) as exc:
            st.error(str(exc))

    report: DeadInstructionReport | None = st.session_state.dead_report
    if report is not None and report.system_prompt != st.session_state.system_prompt:
        st.info(t("dead_stale"))
    elif report is not None:
        for error in report.errors:
            st.warning(t("dead_run_failed", error=error))
        m1, m2, m3 = st.columns(3)
        m1.metric(t("dead_metric_runs"), report.runs)
        m2.metric(t("dead_metric_dead"), f"{len(report.dead)} / {len(report.usage)}")
        m3.metric(
            t("dead_metric_tokens"),
            f"~{report.tokens_saved}",
            f"-{round(100 * report.tokens_saved / report.tokens_before)}%" if report.tokens_before else None,
            delta_color="inverse",
        )
        dead_ids = {u.unit.id for u in report.dead}
        st.dataframe(
            [
                {
                    t("dead_col_id"): u.unit.id,
                    t("dead_col_status"): t("dead_status_dead") if u.unit.id in dead_ids else t("dead_status_alive"),
                    t("dead_col_cited"): f"{u.cited_runs}/{u.runs}",
                    t("dead_col_tokens"): u.tokens,
                    t("dead_col_text"): u.unit.text,
                }
                for u in report.usage
            ],
            hide_index=True,
            width="stretch",
        )
        if report.dead:
            st.caption(t("dead_caveat"))
            col_trim, col_trim_diff = st.columns(2)
            with col_trim:
                st.markdown(f"**{t('dead_trimmed')}**")
                st.code(report.trimmed_system_prompt, language=None, wrap_lines=True)
            with col_trim_diff:
                st.markdown(f"**{t('diff')}**")
                st.code(
                    unified_diff(report.system_prompt, report.trimmed_system_prompt, language=lang),
                    language="diff",
                )

            trimmed = report.trimmed_system_prompt

            def adopt_trimmed() -> None:
                st.session_state.versions.append(st.session_state.system_prompt)
                st.session_state.system_prompt = trimmed
                st.session_state.response = ""
                st.session_state.dead_report = None
                invalidate_attribution()

            st.button(t("adopt"), key="adopt_trimmed", on_click=adopt_trimmed, help=t("adopt_help"))
        else:
            st.success(t("dead_none"))
