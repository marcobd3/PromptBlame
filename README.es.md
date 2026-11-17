<div align="center">

# 🔍 PromptBlame

**Descubre qué instrucción de tu prompt produjo cada parte de la respuesta de un LLM.**

[English](https://github.com/marcobd3/PromptBlame/blob/main/README.md) · **Español**

[![Tests](https://github.com/marcobd3/PromptBlame/actions/workflows/tests.yml/badge.svg)](https://github.com/marcobd3/PromptBlame/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/promptblame?logo=pypi&logoColor=white)](https://pypi.org/project/promptblame/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: AGPL v3](https://img.shields.io/badge/licencia-AGPL--3.0-blue.svg)](https://github.com/marcobd3/PromptBlame/blob/main/LICENSE)
[![Proveedores](https://img.shields.io/badge/LLM-Claude%20%C2%B7%20OpenAI%20%C2%B7%20Gemini%20%C2%B7%20Ollama-6E56CF)](#proveedores)

[Inicio rápido](#inicio-rápido) ·
[Uso](#uso) ·
[Cómo funciona](#cómo-funciona) ·
[Uso como librería](#uso-como-librería) ·
[Desarrollo](#desarrollo)

</div>

---

PromptBlame es un **RAG inverso para prompts**. En lugar de recuperar contexto
para generar una respuesta, parte de la respuesta y localiza qué instrucciones
del *system prompt* y del *user prompt* la causaron. Con ese mapa propone una
nueva versión del system prompt que toca sólo las instrucciones responsables.

Funciona a nivel de **instrucción** y con **modelos cerrados**: no necesita
logits, atención ni pesos, sólo la API del proveedor.

<p align="center">
  <img src="https://raw.githubusercontent.com/marcobd3/PromptBlame/main/docs/es/vista-atribucion.png" alt="Ventana de atribución: la respuesta dividida en bloques de colores y, a la derecha, la cita del prompt de la que procede cada bloque" width="900">
</p>

## Características

- **Atribución por bloques.** La respuesta se resalta en bloques de colores y
  cada uno enlaza con la cita literal del system prompt o del user prompt de la
  que procede, con su nivel de confianza y una explicación.
- **Citas siempre literales.** El juez sólo devuelve identificadores; los
  offsets se calculan en Python, así que una cita no puede inventarse.
- **Instrucciones ignoradas a la vista.** Lista las instrucciones sin efecto
  visible en la respuesta, que suelen ser las que el modelo está pasando por alto.
- **Verificación por ablación (opcional).** Confirma cada atribución
  regenerando la respuesta sin la instrucción citada.
- **Criterios de evaluación propios.** Una caja de instrucciones personalizadas
  para decirle al juez cómo evaluar: qué cuenta como causa, qué ignorar, cómo
  de estricto ser.
- **Mejora guiada del system prompt.** Describe lo que quieres cambiar y
  obtienes una nueva versión, la tabla de cambios y el diff.
- **Multiproveedor.** Claude (por defecto), OpenAI, Google Gemini y cualquier
  endpoint compatible con la API de OpenAI (Ollama, OpenRouter, Mistral, Groq,
  vLLM, LM Studio…). El modelo que responde y el modelo juez se eligen por
  separado.
- **Tema claro y oscuro**, siguiendo el de Streamlit.
- **Interfaz en inglés y en español.** Se muestra en español si el navegador
  está en español y en inglés en cualquier otro caso; se puede cambiar en la
  barra lateral. El juez y el reescritor redactan sus explicaciones en el mismo
  idioma.

## Inicio rápido

Requisitos: Python 3.11 o superior y una API key del proveedor que vayas a usar
(o un servidor local como Ollama, que no la necesita).
PromptBlame está publicado en [PyPI](https://pypi.org/project/promptblame/), así
que se instala con `pip`:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "promptblame[all]"
export ANTHROPIC_API_KEY="sk-ant-..."   # o escríbela en la barra lateral
promptblame
```

La app se abre en <http://localhost:8501> con un ejemplo cargado. Los
argumentos se pasan a Streamlit, p. ej. `promptblame --server.port 8600`.

### Extras

El paquete base trae la librería y los SDK de Anthropic y de OpenAI, así que
funciona con Claude, OpenAI y cualquier endpoint compatible con OpenAI (Ollama,
OpenRouter, Mistral, vLLM…). Añade lo que necesites:

```bash
pip install promptblame                    # librería: Claude, OpenAI y compatibles
pip install "promptblame[app]"             # + interfaz de Streamlit (comando promptblame)
pip install "promptblame[gemini]"          # + Google Gemini
pip install "promptblame[all]"             # todo
```

### Desde el código fuente

```bash
git clone https://github.com/marcobd3/PromptBlame.git
cd PromptBlame
pip install -e ".[all]"
streamlit run app.py
```

`streamlit run app.py` ejecuta siempre el código de `src/`, aunque haya otro
`promptblame` instalado. `requirements.txt` instala el repositorio con todos los extras, para
plataformas que sólo leen ese archivo (p. ej. Streamlit Community Cloud).

## Uso

### 1 · Respuesta y atribución

<p align="center">
  <img src="https://raw.githubusercontent.com/marcobd3/PromptBlame/main/docs/es/pestana-1.png" alt="Pestaña 1: entrada a la izquierda, salida del servicio a la derecha y, debajo, la sección de atribución con sus instrucciones" width="900">
</p>

La entrada está a la izquierda, la salida del servicio a la derecha y, debajo de
las dos, la sección de atribución.

1. Escribe un system prompt y un user prompt, y pulsa **Generar respuesta**.
   La respuesta aparece a la derecha, en la caja de salida; también puedes
   pegar ahí una respuesta que ya tengas.
2. En la sección **Atribución**, debajo, añade si quieres tus instrucciones de
   atribución y pulsa **Ver atribución**. Se abre una ventana con la respuesta dividida en
   bloques de colores y, a la derecha, la cita de la que procede cada bloque.
   Al pasar el ratón por un bloque se resalta su cita; al hacer clic se salta a ella.
3. Los bloques grises no proceden de ninguna instrucción: son conocimiento
   propio del modelo.

### 2 · Mejorar el system prompt

<p align="center">
  <img src="https://raw.githubusercontent.com/marcobd3/PromptBlame/main/docs/es/pestana-2.png" alt="Pestaña 2 con la mejora pedida, el resumen, la tabla de cambios y la nueva versión del system prompt" width="900">
</p>

Toma la última respuesta, la mejora que describas y el mapa de atribución, y
genera una nueva versión del system prompt con un resumen, la tabla de cambios
(qué instrucción se modifica, elimina o añade y por qué) y el diff. Con **Usar
esta versión en la pestaña 1** pasas a probarla; las versiones anteriores
quedan guardadas en la sesión.

### Instrucciones personalizadas de evaluación

En la sección **Atribución** de la pestaña 1 hay una caja opcional para dar al
juez contexto y criterios propios. Por ejemplo:

```text
- El tono y el idioma sólo cuentan como causa si la respuesta se aparta de lo habitual.
- Considera conocimiento del modelo cualquier dato que no aparezca en los prompts.
- Sé estricto: usa confianza "alta" sólo si la instrucción lo exige literalmente.
```

Los criterios se añaden al prompt del juez de atribución y, si dejas marcada la
casilla, también al de la reescritura del system prompt. Cambiarlos invalida la
atribución en caché, así que la siguiente consulta se evalúa con los nuevos
criterios. El formato de salida y la regla de citar sólo identificadores
existentes se mantienen siempre.

### Configuración

Todo se ajusta en la barra lateral:

| Opción | Por defecto | Descripción |
|---|---|---|
| Idioma | el del navegador (inglés si no es español) | Idioma de la interfaz y de las explicaciones del juez y del reescritor. |
| Proveedor y modelo del servicio | Anthropic, `claude-opus-5-5` | Genera la respuesta que se analiza y las regeneraciones de la ablación. |
| Esfuerzo del servicio | `medium` | Esfuerzo de razonamiento de la generación. |
| Proveedor y modelo del juez | Anthropic, `claude-opus-5-5` | Juez de atribución y reescritor del system prompt. |
| Esfuerzo del juez | `high` | Más esfuerzo, atribuciones más finas. |
| Credenciales | variables de entorno | API key de cada proveedor en uso y, para el endpoint compatible, su URL base. |
| Verificar con ablación | desactivado | Confirma cada atribución regenerando sin la instrucción. |
| Máx. instrucciones a ablacionar | `8` | Límite de regeneraciones (se eligen las más citadas). |

El servicio y el juez son independientes: puedes analizar la respuesta de un
modelo local de Ollama con Claude como juez, o comparar cómo atribuyen dos
proveedores la misma respuesta. La lista de modelos es una sugerencia; se
puede escribir cualquier otro identificador.

### Proveedores

| Proveedor | Variable de entorno | Salida estructurada del juez | Esfuerzo |
|---|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `output_config.format` con JSON Schema | `output_config.effort` |
| OpenAI | `OPENAI_API_KEY` | `response_format` `json_schema` estricto | `reasoning_effort` |
| Google Gemini | `GEMINI_API_KEY` o `GOOGLE_API_KEY` | `response_json_schema` | `thinking_level` |
| Compatible con OpenAI | `OPENAI_COMPATIBLE_API_KEY` (opcional), `OPENAI_COMPATIBLE_BASE_URL` | `json_schema` → `json_object` → esquema en el prompt | no se envía |

URLs base habituales para el endpoint compatible:

| Servicio | URL base |
|---|---|
| Ollama (por defecto) | `http://localhost:11434/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Groq | `https://api.groq.com/openai/v1` |

Con Claude Opus 5.5, Fable 5.2 y Sonnet 5.5 se activan los *fallbacks* del
servidor: si el clasificador de seguridad rechaza una petición, la API la
reintenta con otro modelo en la misma llamada.

## Cómo funciona

```mermaid
flowchart LR
    P["System prompt<br/>+ user prompt"] --> SEG["Segmentación<br/>determinista"]
    R["Respuesta"] --> SEG
    SEG -->|"S1… U1… R1…"| J["Juez LLM<br/>(structured outputs)"]
    C["Criterios<br/>personalizados"] -.-> J
    J -->|"ids + confianza"| B["Agrupación<br/>en bloques"]
    B --> A{"¿Ablación?"}
    A -->|sí| V["Regenerar sin cada<br/>instrucción y comparar"]
    A -->|no| M["Mapa de atribución"]
    V --> M
    M --> UI["Vista por bloques"]
    M --> RW["Reescritura del<br/>system prompt"]
```

**1. Segmentación.** Los prompts se dividen de forma determinista en
instrucciones (líneas, viñetas y frases: `S1, S2…` para el system prompt,
`U1, U2…` para el user prompt) y la respuesta en segmentos (`R1, R2…`), con
sus offsets exactos en el texto original.

**2. Juez LLM.** Un modelo juez recibe todas las unidades numeradas y devuelve,
mediante *structured outputs*, las fuentes de cada segmento con una confianza
(alta, media o baja) y una explicación en el idioma elegido. Como el modelo sólo devuelve
identificadores, las citas son siempre literales; los identificadores que no
existen se descartan. Los segmentos contiguos de un mismo párrafo con las
mismas fuentes se agrupan en bloques.

**3. Verificación por ablación (opcional).** Por cada instrucción citada se
regenera la respuesta *sin* esa instrucción y se mide cuánto cambia cada bloque
que la cita:

$$\text{efecto}(B, S) = \text{sim}(B, \text{control}) - \text{sim}(B, \text{sin } S)$$

donde *control* es otra generación con el prompt completo, lo que descuenta la
variación natural entre generaciones. Un efecto ≥ 0,15 marca la atribución como
**confirmada**. Cuesta una llamada por instrucción más una de control, en paralelo.

**4. Reescritura.** El mapa de atribución (bloques, causas, confianza, efecto de
ablación e instrucciones sin efecto) se pasa al reescritor junto con la mejora
pedida. El reescritor cambia primero las instrucciones que causan los bloques
afectados, refuerza las que no tuvieron efecto y deja intacto lo demás.

## Arquitectura

```text
PromptBlame/
├── app.py                        # Atajo para `streamlit run app.py` desde el repositorio
├── src/promptblame/
│   ├── __init__.py               # API pública y versión
│   ├── segmentation.py           # Segmentación determinista en unidades con offsets
│   ├── llm.py                    # Cliente multiproveedor: texto y JSON estructurado
│   ├── attribution.py            # Juez LLM, agrupación en bloques y ablación
│   ├── rewrite.py                # Reescritura del system prompt y diff
│   ├── render.py                 # Vista HTML de bloques de colores y citas
│   ├── app.py                    # Interfaz de Streamlit (extra [app])
│   ├── i18n.py                   # Textos de la interfaz en inglés y español
│   └── cli.py                    # Comando `promptblame`
├── tests/                        # Tests con los clientes de los proveedores simulados
└── docs/                         # Capturas (en inglés; en español, en docs/es/)
```

La librería no depende de Streamlit: la interfaz es una capa fina sobre ella y
se instala con el extra `[app]`.

## Uso como librería

```python
from promptblame import LLM, attribute, rewrite_system_prompt, unified_diff, verify_by_ablation

judge = LLM(model="claude-opus-5-5")  # lee ANTHROPIC_API_KEY
service = LLM(model="gpt-6.1-sol", provider="openai")

system_prompt = "Eres un asistente de soporte.\nResponde siempre en español."
user_prompt = "¿Dónde está mi pedido?"
response = service.text(system_prompt, user_prompt)

attr = attribute(
    judge,
    system_prompt,
    user_prompt,
    response,
    instructions="Considera conocimiento del modelo cualquier dato que no esté en los prompts.",
    language="es",  # idioma de las explicaciones; por defecto "en"
)
verify_by_ablation(service, attr)  # opcional

for block in attr.blocks:
    sources = ", ".join(f"{link.unit.id} ({link.confidence})" for link in block.sources)
    print(f"{block.id}: {block.text!r} ← {sources or 'conocimiento del modelo'}")

print("Sin efecto:", [u.id for u in attr.unused_sources])

result = rewrite_system_prompt(judge, attr, "Que pida el número de pedido.")
print(unified_diff(system_prompt, result.new_system_prompt))
```

## Desarrollo

```bash
pip install -e ".[all]" --group dev   # pip 25.1 o superior
ruff check . && ruff format --check .
mypy
pytest
```

Los tests simulan los clientes de cada proveedor, así que no necesitan API key
ni gastan tokens. Cubren la segmentación, el juez, la agrupación en bloques, la
ablación, la reescritura, la vista HTML, los cuatro proveedores, los casos de
seguridad y un recorrido completo de la interfaz con `streamlit.testing`. En
GitHub Actions se ejecutan con Python 3.11 a 3.13, junto con ruff, mypy y la
construcción del paquete, en cada *push* y *pull request*.

### Publicar una versión

1. Sube `__version__` en `src/promptblame/__init__.py` y anota los cambios en
   `CHANGELOG.md`.
2. Crea en GitHub una release con la etiqueta `vX.Y.Z` (la misma versión).
3. El workflow `publish.yml` construye el paquete y lo publica en PyPI con
   *Trusted Publishing*, sin tokens guardados. Falla si la etiqueta no coincide
   con la versión.

## Seguridad

- **API keys.** Las keys del entorno (`ANTHROPIC_API_KEY`, etc.) se leen en el
  servidor y nunca se envían al navegador. Las que se escriben en la barra
  lateral sólo viven en la sesión de Streamlit y no se guardan ni se registran.
- **Despliegues públicos.** Si publicas la app con una key en el entorno,
  cualquier visitante gastará tu cuota. En ese caso no definas keys en el
  servidor y deja que cada usuario escriba la suya, o protege la app con
  autenticación. El proveedor «compatible» hace que el servidor llame a la URL
  que escriba el usuario (sólo `http`/`https`); no lo expongas en una red con
  servicios internos.
- **Contenido no confiable.** Prompts y respuestas se escapan en la vista HTML,
  la respuesta se muestra como texto (no como Markdown, para que no cargue
  imágenes externas) y la salida JSON de los modelos se valida antes de usarla.
  Los prompts del juez y del reescritor les indican que traten el contenido
  analizado como datos, aunque ningún modelo es inmune a la inyección de
  prompts.

Para informar de una vulnerabilidad, consulta [SECURITY.md](https://github.com/marcobd3/PromptBlame/blob/main/SECURITY.md).

## Limitaciones conocidas

- La atribución del juez es una hipótesis del propio modelo. La ablación la
  contrasta, pero mide similitud léxica, no semántica.
- Las instrucciones redundantes pueden no superar la ablación aunque influyan:
  si dos instrucciones piden lo mismo, quitar una sola no cambia la respuesta.
- La segmentación por frases es heurística y está pensada para español e inglés.
- Con modelos pequeños o sin salida estructurada estricta, el juez puede
  devolver identificadores de más o de menos; se descartan los que no existen
  y se avisa de los segmentos sin atribución.

## Contribuir

Las *issues* y *pull requests* son bienvenidas. Antes de abrir una PR, ejecuta
`ruff`, `mypy` y `pytest`, y añade tests para el comportamiento nuevo.

## Licencia

Distribuido bajo la licencia [GNU AGPL-3.0](https://github.com/marcobd3/PromptBlame/blob/main/LICENSE). Si ofreces una versión
modificada de PromptBlame como servicio en red, debes publicar el código fuente
de tus cambios.
