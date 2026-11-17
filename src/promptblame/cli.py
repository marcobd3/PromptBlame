"""Comando ``promptblame``: abre la interfaz de Streamlit instalada con el paquete."""

from __future__ import annotations

import sys
from pathlib import Path

APP_PATH = Path(__file__).with_name("app.py")
# Lo mismo que .streamlit/config.toml del repositorio, que no viaja con el
# paquete: sin telemetría de Streamlit y con la barra de herramientas mínima.
# Los argumentos del usuario van después y tienen prioridad.
DEFAULT_ARGS = ("--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal")


def main(argv: list[str] | None = None) -> int:
    """Ejecuta ``streamlit run`` sobre la app del paquete.

    Los argumentos se pasan a Streamlit, p. ej. ``promptblame --server.port 8600``.
    """
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print(
            'La interfaz necesita Streamlit. Instálala con: pip install "promptblame[app]"',
            file=sys.stderr,
        )
        return 1
    args = sys.argv[1:] if argv is None else argv
    sys.argv = ["streamlit", "run", str(APP_PATH), *DEFAULT_ARGS, *args]
    result = stcli.main()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
