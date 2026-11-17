"""PromptBlame: attribute LLM responses to the prompt instructions behind them.

Public API::

    from promptblame import LLM, attribute, verify_by_ablation, rewrite_system_prompt

    llm = LLM()  # Claude; the API key is read from ANTHROPIC_API_KEY
    attr = attribute(llm, system_prompt, user_prompt, response)
"""

from .attribution import Attribution, Block, SourceLink, attribute, verify_by_ablation
from .llm import DEFAULT_PROVIDER, EFFORTS, LLM, PROVIDERS, LLMError, Provider
from .render import attribution_html
from .rewrite import Rewrite, rewrite_system_prompt, unified_diff
from .segmentation import Unit, segment

__version__ = "0.4.1"

__all__ = [
    "DEFAULT_PROVIDER",
    "EFFORTS",
    "LLM",
    "PROVIDERS",
    "Attribution",
    "Block",
    "LLMError",
    "Provider",
    "Rewrite",
    "SourceLink",
    "Unit",
    "__version__",
    "attribute",
    "attribution_html",
    "rewrite_system_prompt",
    "segment",
    "unified_diff",
    "verify_by_ablation",
]
