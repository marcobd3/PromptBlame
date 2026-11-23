# Cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [0.5.0] - 2026-11-23

### Añadido

- **`.env` automático.** La interfaz, la CLI y la API REST cargan el `.env` del
  directorio de trabajo (con `python-dotenv`, ahora dependencia del paquete)
  sin pisar las variables ya definidas. Además de las API keys admite
  proveedor, modelo y esfuerzo por defecto del servicio y del juez, idioma,
  ablación y token de la API. Plantilla documentada en `.env.example`.
- **CLI para CI y evaluaciones.** `promptblame attribute`, `rewrite` y `dead`
  leen los prompts de ficheros, imprimen un resumen o JSON (`--json`, `-o`) y
  devuelven el código 3 si falla una comprobación (`--fail-on-unsourced`,
  `--min-confidence`, `--fail-on-dead`). `promptblame` sin subcomando sigue
  abriendo la interfaz (también `promptblame ui`).
- **API REST** (extra `[api]`, `promptblame serve`): `/generate`, `/attribute`,
  `/rewrite` y `/dead-instructions` con FastAPI. Las keys y la URL del
  endpoint compatible salen sólo del entorno del servidor; con
  `PROMPTBLAME_API_TOKEN` exige `Authorization: Bearer`.
- **Instrucciones muertas.** Pestaña 3 y `scan_dead_instructions()`: pasa
  varios user prompts N veces por el servicio, atribuye cada respuesta, cuenta
  en cuántas ejecuciones se cita cada instrucción del system prompt y propone
  una versión recortada sin las que nunca se citan, con el ahorro estimado de
  tokens y el diff.
- **Puntuación causal por ablación.** Cada enlace verificado tiene
  `causal_score` (0–1): la fracción del bloque que desaparece al quitar la
  instrucción. La ablación se puede lanzar desde la propia ventana de
  atribución.
- **Confianza por bloque.** Cada bloque muestra una barra de confianza (la del
  juez, promediada con la puntuación causal si hay ablación); los de confianza
  baja se subrayan y los que no vienen de ninguna instrucción se marcan con ⚠
  y un aviso de posible alucinación con el porcentaje de la respuesta afectado.
- `Attribution.to_dict()`, `unsourced_blocks`, `unsourced_share`;
  `Block.confidence` y `confidence_score`.

## [0.4.1] - 2026-11-17

### Cambiado

- Metadatos de PyPI en inglés: descripción, palabras clave, clasificadores
  (inglés y español) y enlace a la documentación. El mensaje del comando
  `promptblame` cuando falta Streamlit también pasa a inglés.

## [0.4.0] - 2026-11-17

Primera versión preparada para PyPI.

### Cambiado

- La pestaña 1 muestra la entrada a la izquierda, la salida del servicio a la
  derecha y, debajo de ambas, la sección de atribución con la caja de
  instrucciones para el juez (antes era un desplegable encima de las
  pestañas). Las citas siguen abriéndose en una ventana emergente.
- Interfaz en inglés por defecto y en español si el navegador está en español,
  con selector de idioma en la barra lateral. `attribute()` y
  `rewrite_system_prompt()` aceptan `language` ("en" por defecto o "es") para
  el idioma de las explicaciones, y los mensajes de `LLMError` pasan a inglés.
- README en inglés; la versión en español está en `README.es.md`.

### Corregido

- `streamlit run app.py` ejecuta siempre el código de `src/` y no una versión
  de `promptblame` instalada antes (`pip install .` sin `-e`, o la caché de
  Streamlit Community Cloud).

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
