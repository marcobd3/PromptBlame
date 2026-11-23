"""``promptblame`` command: the Streamlit UI plus subcommands for CI and evaluations.

::

    promptblame                       # opens the UI (same as `promptblame ui`)
    promptblame --server.port 8600    # UI, with arguments passed on to Streamlit
    promptblame attribute -s system.txt -u user.txt [-r response.txt] [--json]
    promptblame rewrite   -s system.txt -u user.txt -i "Be shorter" [-o new.txt]
    promptblame dead      -s system.txt -u prompts.txt --runs 3 [--fail-on-dead]
    promptblame serve     [--host 127.0.0.1] [--port 8000]   # REST API ([api] extra)

A ``.env`` file in the working directory (or above) is loaded first, so API keys
and provider/model defaults don't need to be repeated. See ``.env.example``.

Exit codes: 0 OK, 1 error, 2 bad arguments, 3 a ``--fail-on-*`` check failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import RoleSettings, load_env, settings

APP_PATH = Path(__file__).with_name("app.py")
# Lo mismo que .streamlit/config.toml del repositorio, que no viaja con el
# paquete: sin telemetría de Streamlit y con la barra de herramientas mínima.
# Los argumentos del usuario van después y tienen prioridad.
DEFAULT_ARGS = ("--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal")

SUBCOMMANDS = ("ui", "attribute", "rewrite", "dead", "serve")
EXIT_CHECK_FAILED = 3


def run_ui(args: list[str]) -> int:
    """Ejecuta ``streamlit run`` sobre la app del paquete con ``args``."""
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print(
            'The UI needs Streamlit. Install it with: pip install "promptblame[app]"',
            file=sys.stderr,
        )
        return 1
    sys.argv = ["streamlit", "run", str(APP_PATH), *DEFAULT_ARGS, *args]
    result = stcli.main()
    return int(result or 0)


# --- Argumentos -----------------------------------------------------------------


def _read(path: str) -> str:
    """Lee un fichero de texto (``-`` = entrada estándar)."""
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def read_user_prompts(path: str) -> list[str]:
    """User prompts de un fichero: JSONL (una cadena o ``{"user_prompt": …}`` por línea)
    o texto con los prompts separados por líneas ``---``."""
    from .dead import split_user_prompts

    text = _read(path)
    if path.endswith((".jsonl", ".ndjson")):
        prompts = []
        for line in text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                item = item.get("user_prompt") or item.get("prompt") or item.get("input")
            if not isinstance(item, str):
                raise ValueError(f"Unrecognised JSONL line in {path}: {line[:80]}")
            prompts.append(item)
        return prompts
    return split_user_prompts(text)


def _add_model_args(parser: argparse.ArgumentParser, role: str, defaults: RoleSettings, what: str) -> None:
    from .llm import EFFORTS, PROVIDERS

    flag = "" if role == "service" else "judge-"
    parser.add_argument(f"--{flag}provider", choices=list(PROVIDERS), default=defaults.provider, help=what)
    parser.add_argument(f"--{flag}model", default=defaults.model, help=f"Model id ({what}).")
    parser.add_argument(f"--{flag}effort", choices=list(EFFORTS), default=defaults.effort)


def build_parser() -> argparse.ArgumentParser:
    cfg = settings()
    common = argparse.ArgumentParser(add_help=False)
    _add_model_args(common, "service", cfg.service, "Service: generates the responses and the ablation runs.")
    _add_model_args(common, "judge", cfg.judge, "Judge: attribution and rewriting.")
    common.add_argument("--base-url", default=cfg.base_url, help="Base URL of the OpenAI-compatible endpoint.")
    common.add_argument("--language", choices=["en", "es"], default=cfg.language or "en")
    common.add_argument("--criteria", default="", help="Custom attribution instructions for the judge (text).")
    common.add_argument("--json", action="store_true", help="Print the full result as JSON.")
    common.add_argument("-o", "--output", help="Also write the result (JSON, or the new prompt) to this file.")

    prompts = argparse.ArgumentParser(add_help=False)
    prompts.add_argument("-s", "--system", required=True, help="System prompt file ('-' = stdin).")

    parser = argparse.ArgumentParser(prog="promptblame", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ui", help="Open the Streamlit UI (extra arguments go to Streamlit).", add_help=False)

    attr = sub.add_parser("attribute", parents=[common, prompts], help="Attribute a response to the prompts.")
    attr.add_argument("-u", "--user", required=True, help="User prompt file.")
    attr.add_argument("-r", "--response", help="Response file. If omitted, the service generates one.")
    attr.add_argument("--ablation", action="store_true", default=cfg.ablation, help="Verify by ablation.")
    attr.add_argument("--max-ablation", type=int, default=cfg.max_ablation)
    attr.add_argument(
        "--fail-on-unsourced",
        type=float,
        metavar="SHARE",
        help="Exit with code 3 if more than SHARE (0-1) of the response comes from no instruction.",
    )
    attr.add_argument(
        "--min-confidence",
        type=float,
        metavar="SCORE",
        help="Exit with code 3 if any sourced block has a confidence below SCORE (0-1).",
    )

    rew = sub.add_parser("rewrite", parents=[common, prompts], help="Generate a new system prompt version.")
    rew.add_argument("-u", "--user", required=True, help="User prompt file.")
    rew.add_argument("-r", "--response", help="Response file. If omitted, the service generates one.")
    rew.add_argument("-i", "--improvement", required=True, help="What you want to improve (text).")
    rew.add_argument("--ablation", action="store_true", default=cfg.ablation)
    rew.add_argument("--max-ablation", type=int, default=cfg.max_ablation)

    dead = sub.add_parser("dead", parents=[common, prompts], help="Find system prompt instructions never cited.")
    dead.add_argument(
        "-u",
        "--user-prompts",
        required=True,
        help="User prompts: .jsonl, or text with prompts separated by '---' lines.",
    )
    dead.add_argument("--runs", type=int, default=1, help="Runs per user prompt (default 1).")
    dead.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Max. share of runs citing an instruction to count it as dead (default 0 = never cited).",
    )
    dead.add_argument("--fail-on-dead", action="store_true", help="Exit with code 3 if any instruction is dead.")
    dead.add_argument("--write-trimmed", help="Write the trimmed system prompt to this file.")

    serve = sub.add_parser("serve", help='Run the REST API (needs the [api] extra: pip install "promptblame[api]").')
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


# --- Subcomandos ---------------------------------------------------------------


def _llms(ns: argparse.Namespace) -> tuple[Any, Any]:
    from .llm import LLM

    service = LLM(model=ns.model, provider=ns.provider, base_url=ns.base_url if ns.provider == "compatible" else None)
    judge = LLM(
        model=ns.judge_model,
        provider=ns.judge_provider,
        base_url=ns.base_url if ns.judge_provider == "compatible" else None,
    )
    return service, judge


def _attribution(ns: argparse.Namespace, service: Any, judge: Any) -> Any:
    from .attribution import attribute, verify_by_ablation

    system_prompt, user_prompt = _read(ns.system), _read(ns.user)
    if ns.response:
        response = _read(ns.response)
    else:
        print(f"Generating the response with {ns.model}…", file=sys.stderr)
        response = service.text(system_prompt, user_prompt, effort=ns.effort)
    attr = attribute(
        judge,
        system_prompt,
        user_prompt,
        response,
        effort=ns.judge_effort,
        instructions=ns.criteria,
        language=ns.language,
    )
    if ns.ablation and attr.blocks:
        print("Verifying by ablation…", file=sys.stderr)
        verify_by_ablation(service, attr, effort=ns.effort, max_sources=ns.max_ablation)
    return attr


def _emit(ns: argparse.Namespace, data: dict[str, Any], summary: str) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    print(text if ns.json else summary)
    if ns.output:
        Path(ns.output).write_text(text + "\n", encoding="utf-8")


def attribution_summary(attr: Any) -> str:
    lines = []
    for block in attr.blocks:
        if block.sources:
            refs = []
            for link in block.sources:
                ref = f"{link.unit.id}:{link.confidence}"
                if link.causal_score is not None:
                    ref += f" causal={link.causal_score:.2f}" + (" ✓" if link.verified else " ✗")
                refs.append(ref)
            src = ", ".join(refs) + f"  [confidence {round((block.confidence_score or 0) * 100)}%]"
        else:
            src = "⚠ no source (model knowledge or possible hallucination)"
        lines.append(f"{block.id} {block.text[:70]!r}\n    ← {src}")
    if attr.unused_sources:
        lines.append("No visible effect: " + ", ".join(u.id for u in attr.unused_sources))
    lines.append(f"Unsourced share of the response: {round(attr.unsourced_share * 100)}%")
    lines.extend(attr.notes)
    return "\n".join(lines)


def cmd_attribute(ns: argparse.Namespace) -> int:
    service, judge = _llms(ns)
    attr = _attribution(ns, service, judge)
    _emit(ns, attr.to_dict(), attribution_summary(attr))
    failed = False
    if ns.fail_on_unsourced is not None and attr.unsourced_share > ns.fail_on_unsourced:
        print(
            f"FAIL: {round(attr.unsourced_share * 100)}% of the response comes from no instruction "
            f"(limit {round(ns.fail_on_unsourced * 100)}%).",
            file=sys.stderr,
        )
        failed = True
    if ns.min_confidence is not None:
        low = [b.id for b in attr.blocks if b.confidence_score is not None and b.confidence_score < ns.min_confidence]
        if low:
            print(f"FAIL: blocks below confidence {ns.min_confidence}: {', '.join(low)}.", file=sys.stderr)
            failed = True
    return EXIT_CHECK_FAILED if failed else 0


def cmd_rewrite(ns: argparse.Namespace) -> int:
    from .rewrite import rewrite_system_prompt, unified_diff

    service, judge = _llms(ns)
    attr = _attribution(ns, service, judge)
    result = rewrite_system_prompt(
        judge, attr, ns.improvement, effort=ns.judge_effort, instructions=ns.criteria, language=ns.language
    )
    data = {
        "attribution": attr.to_dict(),
        "new_system_prompt": result.new_system_prompt,
        "changes": result.changes,
        "summary": result.summary,
        "diff": unified_diff(attr.system_prompt, result.new_system_prompt, language=ns.language),
    }
    print(json.dumps(data, ensure_ascii=False, indent=2) if ns.json else result.summary + "\n\n" + data["diff"])
    if ns.output:
        Path(ns.output).write_text(result.new_system_prompt, encoding="utf-8")
    return 0


def dead_summary(report: Any) -> str:
    lines = [f"{report.runs} runs. Citations per system prompt instruction:"]
    dead_ids = {u.unit.id for u in report.dead}
    for usage in report.usage:
        mark = "✗ dead" if usage.unit.id in dead_ids else "  "
        lines.append(
            f"{mark:>6} {usage.unit.id:>4} {usage.cited_runs}/{usage.runs} runs  ~{usage.tokens} tok  {usage.unit.text[:70]!r}"
        )
    if report.dead:
        lines.append(
            f"Trimming {len(report.dead)} instruction(s) saves ~{report.tokens_saved} tokens per call "
            f"({report.tokens_before} → {report.tokens_after}). Review before adopting: rarely triggered rules "
            "(safety, edge cases) may look dead."
        )
    else:
        lines.append("No dead instructions.")
    lines.extend(f"Run failed: {e}" for e in report.errors)
    return "\n".join(lines)


def cmd_dead(ns: argparse.Namespace) -> int:
    from .dead import scan_dead_instructions

    service, judge = _llms(ns)
    prompts = read_user_prompts(ns.user_prompts)
    total = len([p for p in prompts if p.strip()]) * max(1, ns.runs)
    print(f"{total} runs ({total * 2} calls)…", file=sys.stderr)
    report = scan_dead_instructions(
        service,
        judge,
        _read(ns.system),
        prompts,
        runs_per_prompt=ns.runs,
        threshold=ns.threshold,
        service_effort=ns.effort,
        judge_effort=ns.judge_effort,
        instructions=ns.criteria,
        language=ns.language,
    )
    _emit(ns, report.to_dict(), dead_summary(report))
    if ns.write_trimmed:
        Path(ns.write_trimmed).write_text(report.trimmed_system_prompt + "\n", encoding="utf-8")
    if ns.fail_on_dead and report.dead:
        print(f"FAIL: dead instructions: {', '.join(u.unit.id for u in report.dead)}.", file=sys.stderr)
        return EXIT_CHECK_FAILED
    return 0


def cmd_serve(ns: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print('The REST API needs FastAPI and Uvicorn: pip install "promptblame[api]"', file=sys.stderr)
        return 1
    from .api import create_app

    uvicorn.run(create_app(), host=ns.host, port=ns.port)
    return 0


COMMANDS = {"attribute": cmd_attribute, "rewrite": cmd_rewrite, "dead": cmd_dead, "serve": cmd_serve}


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Sin subcomando (o con ``ui``) abre la interfaz de Streamlit."""
    args = sys.argv[1:] if argv is None else argv
    load_env()
    if not args or args[0] not in SUBCOMMANDS or args[0] == "ui":
        if args and args[0] in ("-h", "--help"):
            build_parser().print_help()
            return 0
        return run_ui(args[1:] if args and args[0] == "ui" else args)
    ns = build_parser().parse_args(args)
    from .llm import LLMError

    try:
        return COMMANDS[ns.command](ns)
    except (LLMError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
