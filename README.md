# PromptBlame

**¿Qué instrucción de tu prompt produjo cada parte de la respuesta?**

PromptBlame es un "RAG inverso" para prompts: en lugar de recuperar contexto
para generar una respuesta, parte de la respuesta y localiza qué instrucciones
del *system prompt* y del *user prompt* la causaron. Con ese mapa propone una
versión mejorada del system prompt, tocando sólo las instrucciones responsables.

Es una app de [Streamlit](https://streamlit.io) en Python que usa Claude a
través de la API de Anthropic.

![Ventana de atribución en modo oscuro, con datos de ejemplo](docs/vista-atribucion.png)

La vista se adapta al tema claro u oscuro de Streamlit.

## Qué hace

**Pestaña 1 · Respuesta y atribución**

1. Escribe un system prompt y un user prompt, y pulsa **Generar respuesta**
   (o pega en la caja de salida una respuesta que ya tengas).
2. Pulsa **Ver atribución**. Se abre una ventana emergente con la respuesta
   dividida en bloques de colores y, a la derecha, cada bloque enlaza con la cita literal del system
   prompt o del user prompt de donde viene, con su nivel de confianza y una
   explicación breve. Al pasar el ratón por un bloque se resalta su cita, y al
   hacer clic se salta a ella.
3. Los bloques grises no proceden de ninguna instrucción (son conocimiento
   propio del modelo). Debajo se listan las instrucciones **sin efecto
   visible**, que suelen ser las que el modelo está ignorando.

**Pestaña 2 · Mejorar el system prompt**

Toma la última respuesta, una descripción de la mejora que quieres y el mapa de
atribución, y genera una nueva versión del system prompt. Muestra el resumen,
la tabla de cambios (qué instrucción se modifica, elimina o añade y por qué) y
el diff. Con **Usar esta versión en la pestaña 1** pasas a probarla; las
versiones anteriores quedan guardadas en la sesión.

## Cómo funciona la atribución

Con modelos cerrados no hay acceso a logits, atención ni pesos, así que
PromptBlame combina dos técnicas que sólo necesitan la API:

1. **Juez LLM sobre unidades numeradas.** Los prompts se segmentan de forma
   determinista en instrucciones (líneas, viñetas y frases: `S1, S2…` para el
   system prompt, `U1, U2…` para el user prompt) y la respuesta en segmentos
   (`R1, R2…`). Un modelo de Claude recibe todo numerado y devuelve, con
   *structured outputs*, las fuentes de cada segmento. Como los offsets se
   calculan en Python y el modelo sólo devuelve identificadores, **las citas
   son siempre literales** y no pueden inventarse. Los segmentos contiguos de
   un mismo párrafo con las mismas fuentes se agrupan en bloques.
2. **Verificación por ablación (opcional).** Inspirada en
   [ContextCite](https://github.com/MadryLab/context-cite), pero a nivel de
   instrucción: por cada instrucción citada se regenera la respuesta *sin* esa
   instrucción y se mide cuánto cambia cada bloque que la cita. El efecto es
   `sim(bloque, control) − sim(bloque, sin la instrucción)`, donde *control*
   es otra generación con el prompt completo; así se descuenta la variación
   natural entre generaciones. Un efecto ≥ 0,15 marca la atribución como
   **confirmada**. Cuesta una llamada por instrucción más una de control
   (limitado por defecto a 8 instrucciones, en paralelo).

### Diferencia con ContextCite

ContextCite atribuye a nivel de frase del *contexto* (documentos recuperados) y
ajusta un modelo sustituto lineal sobre muchas ablaciones aleatorias usando las
probabilidades del modelo. PromptBlame trabaja a nivel de **instrucción** del
prompt y con **modelos cerrados**, donde no hay probabilidades: usa un juez LLM
para la hipótesis y ablaciones dirigidas con similitud textual para
verificarla.

## Instalación y uso

Requiere Python 3.10 o superior y una API key de Anthropic.

```bash
git clone https://github.com/marcobd3/PromptBlame.git
cd PromptBlame
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # o escríbela en la barra lateral
streamlit run app.py
```

En la barra lateral puedes elegir:

| Opción | Por defecto | Para qué |
|---|---|---|
| Modelo del servicio | `claude-opus-5-5` | El modelo que genera la respuesta que se analiza. |
| Esfuerzo del servicio | `medium` | `output_config.effort` de la generación. |
| Modelo de atribución y reescritura | `claude-opus-5-5` | El juez y el reescritor. |
| Esfuerzo de atribución | `high` | Más esfuerzo, atribuciones más finas. |
| Verificar con ablación | desactivado | Confirma cada atribución regenerando sin la instrucción. |

Con Claude Opus 5.5, Fable 5.2 y Sonnet 5.5 se activan los *fallbacks* del
servidor (`fallbacks: "default"`): si el clasificador de seguridad rechaza una
petición, la API la reintenta con otro modelo en la misma llamada.

## Estructura

```
app.py                     Interfaz de Streamlit (las dos pestañas)
promptblame/
  segmentation.py          Segmentación determinista en unidades con offsets
  llm.py                   Envoltorio de la API de Claude (texto y JSON)
  attribution.py           Juez LLM, agrupación en bloques y ablación
  rewrite.py               Reescritura del system prompt y diff
  render.py                Vista HTML de bloques de colores y citas
tests/                     Pruebas con la API simulada (no gastan tokens)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas simulan el cliente de Anthropic, así que no necesitan API key.

## Limitaciones conocidas

- La atribución del juez es una hipótesis del propio modelo; la ablación la
  contrasta, pero mide similitud léxica, no semántica.
- Instrucciones redundantes pueden no superar la ablación aunque influyan: si
  dos instrucciones piden lo mismo, quitar una sola no cambia la respuesta.
- La segmentación por frases es heurística (español e inglés).

## Licencia

[AGPL-3.0](LICENSE). Si ofreces PromptBlame modificado como servicio en red,
debes publicar el código fuente de tus cambios.
