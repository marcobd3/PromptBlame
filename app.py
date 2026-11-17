"""Punto de entrada para ``streamlit run app.py`` desde una copia del repositorio.

La interfaz vive en ``promptblame.app`` para que se distribuya con el paquete
(``pip install "promptblame[app]"`` y luego ``promptblame``). Este archivo sólo
la ejecuta, así que sirve también para Streamlit Community Cloud.
"""

import runpy

runpy.run_module("promptblame.app", run_name="__main__")
