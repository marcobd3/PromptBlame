"""Punto de entrada para ``streamlit run app.py`` desde una copia del repositorio.

La interfaz vive en ``promptblame.app`` para que se distribuya con el paquete
(``pip install "promptblame[app]"`` y luego ``promptblame``). Este archivo sólo
la ejecuta, así que sirve también para Streamlit Community Cloud.

Antes de importarla pone ``src/`` el primero en ``sys.path``: así siempre se
ejecuta el código de esta copia del repositorio y no una versión de
``promptblame`` instalada antes con ``pip install .`` (sin ``-e``) o que
Streamlit Community Cloud conserva en caché mientras no cambie
``requirements.txt``.
"""

import runpy
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parent / "src")
if SRC in sys.path:
    sys.path.remove(SRC)
sys.path.insert(0, SRC)

runpy.run_module("promptblame.app", run_name="__main__")
