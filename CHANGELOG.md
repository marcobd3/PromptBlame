# Cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [0.4.0] - sin publicar

Primera versión preparada para PyPI.

### Añadido

- Paquete instalable con `pip install promptblame` y comando `promptblame`
  que abre la interfaz.
- Los SDK de Anthropic y de OpenAI se instalan por defecto (el de OpenAI sirve
  también para los endpoints compatibles). Extras `[app]` (Streamlit),
  `[gemini]` y `[all]`.
- API pública en `promptblame` (`from promptblame import LLM, attribute…`),
  anotaciones de tipos (`py.typed`) y comprobación con mypy.
- Lint y formato con ruff, construcción del paquete en CI y workflow de
  publicación en PyPI con *Trusted Publishing*.
- Validación de la salida JSON del juez y del reescritor.

### Cambiado

- Código en `src/promptblame/` y metadatos sólo en `pyproject.toml`
  (backend hatchling). La versión se define en un único sitio.
- Streamlit deja de ser una dependencia obligatoria de la librería.
- Versiones mayores de los SDK acotadas.

### Seguridad

- La API key del entorno ya no se precarga en el campo de la barra lateral,
  porque su valor llegaba al navegador de cualquier visitante.
- La respuesta del modelo en la pestaña 2 se muestra como texto y no como
  Markdown, para que no pueda cargar imágenes externas.
- La URL base del proveedor compatible debe ser `http` o `https`.
- Los prompts del juez y del reescritor tratan el contenido analizado como datos.
- Acciones de GitHub fijadas por SHA y permisos mínimos en los workflows.

## [0.3.0]

- Instrucciones personalizadas de evaluación, README y CI.
