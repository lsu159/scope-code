"""Abstract LLM adapter — model-agnostic interface."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class Message:
    """A single chat message."""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    model: str
    api_key: str
    api_base: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.1
    extra: Dict[str, Any] = field(default_factory=dict)


class LLMAdapter(ABC):
    """Abstract base class for all LLM providers.

    Each provider (Claude, OpenAI, Gemini, etc.) implements this
    interface, ensuring the framework is model-agnostic.

    Two core methods:
        - chat(): free-form text generation
        - structured_output(): schema-constrained JSON output
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        **kwargs
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: List of conversation messages.
            **kwargs: Provider-specific overrides.

        Returns:
            The model's text response.
        """
        ...

    @abstractmethod
    async def structured_output(
        self,
        messages: List[Message],
        output_schema: dict,
        **kwargs
    ) -> dict:
        """Request a structured JSON output matching a schema.

        Args:
            messages: List of conversation messages.
            output_schema: JSON Schema the output must conform to.
            **kwargs: Provider-specific overrides.

        Returns:
            Parsed JSON dict matching the schema.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier (e.g., 'claude', 'openai')."""
        ...

    def _build_system_prompt(self, base: str) -> str:
        """Wrap a system prompt with Scope Code framework instructions.

        All LLM calls in the pipeline share this instruction base
        to ensure consistent behavior: the AI acts as a disciplined
        software engineer, not a code-generation machine.
        """
        framework_instruction = (
            "You are a Reliable Software Engineering Agent. "
            "Your core principles:\n"
            "1. Minimum Scope Editing — only change what must change.\n"
            "2. Explain Before Edit — every change must have a reason.\n"
            "3. Scope First — define boundaries before acting.\n"
            "4. Evidence Chain — every decision must be traceable.\n"
            "5. Human-AI Collaboration — the user has final authority.\n\n"
            "Before suggesting any code change, answer:\n"
            "- Why must this change?\n"
            "- Why can't other files handle this?\n"
            "- What must NOT be touched?\n"
        )
        return f"{framework_instruction}\n\n{base}"
