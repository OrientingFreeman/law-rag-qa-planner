"""Generation package public API with lazy imports to avoid reasoning cycles."""
from __future__ import annotations

from typing import Any

__all__ = [
    "AnswerResult",
    "DeterministicProvider",
    "DisabledProvider",
    "GenerationError",
    "GenerationOutput",
    "LlmProvider",
    "OpenAICompatibleProvider",
    "generate_grounded_answer",
    "provider_from_env",
]


def __getattr__(name: str) -> Any:
    if name in {"AnswerResult", "generate_grounded_answer"}:
        from law_rag.generation.answer import AnswerResult, generate_grounded_answer
        return {"AnswerResult": AnswerResult, "generate_grounded_answer": generate_grounded_answer}[name]
    if name in {
        "DeterministicProvider", "DisabledProvider", "GenerationError",
        "GenerationOutput", "LlmProvider", "OpenAICompatibleProvider", "provider_from_env",
    }:
        from law_rag.generation import providers
        return getattr(providers, name)
    raise AttributeError(name)
