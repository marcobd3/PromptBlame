"""PromptBlame: attribute LLM responses to the prompt instructions behind them.

Public API::

    from promptblame import LLM, attribute, verify_by_ablation, rewrite_system_prompt, scan_dead_instructions

    llm = LLM()  # Claude; the API key is read from ANTHROPIC_API_KEY
    attr = attribute(llm, system_prompt, user_prompt, response)
    attr.to_dict()  # JSON-serialisable, for CI and evaluations

The same features are available from the command line (``promptblame attribute``,
``rewrite``, ``dead``) and as a REST API (``promptblame serve``, ``[api]`` extra).
"""

from .attribution import Attribution, Block, SourceLink, attribute, verify_by_ablation
from .config import load_env
from .dead import DeadInstructionReport, InstructionUsage, dead_instructions, scan_dead_instructions, trim_system_prompt
from .llm import DEFAULT_PROVIDER, EFFORTS, LLM, PROVIDERS, LLMError, Provider
from .render import attribution_html
from .rewrite import Rewrite, rewrite_system_prompt, unified_diff
from .segmentation import Unit, segment

__version__ = "0.5.0"

__all__ = [
    "DEFAULT_PROVIDER",
    "EFFORTS",
    "LLM",
    "PROVIDERS",
    "Attribution",
    "Block",
    "DeadInstructionReport",
    "InstructionUsage",
    "LLMError",
    "Provider",
    "Rewrite",
    "SourceLink",
    "Unit",
    "__version__",
    "attribute",
    "attribution_html",
    "dead_instructions",
    "load_env",
    "rewrite_system_prompt",
    "scan_dead_instructions",
    "segment",
    "trim_system_prompt",
    "unified_diff",
    "verify_by_ablation",
]
