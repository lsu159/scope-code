"""LLM factory — create adapters by provider name."""

from typing import Optional

from .base import LLMAdapter, LLMConfig
from .claude import ClaudeAdapter
from .openai import OpenAIAdapter
from .gemini import GeminiAdapter
from .deepseek import DeepSeekAdapter


# Registry of known providers
_PROVIDERS = {
    "claude": ClaudeAdapter,
    "anthropic": ClaudeAdapter,
    "openai": OpenAIAdapter,
    "gpt": OpenAIAdapter,
    "gemini": GeminiAdapter,
    "google": GeminiAdapter,
    "deepseek": DeepSeekAdapter,
}


def create_llm(
    provider: str,
    model: str,
    api_key: str,
    api_base: Optional[str] = None,
    **kwargs
) -> LLMAdapter:
    """Create an LLM adapter instance.

    Args:
        provider: Provider name ('claude', 'openai', etc.).
        model: Model identifier (e.g., 'claude-sonnet-5-20251001').
        api_key: API key for authentication.
        api_base: Optional custom API base URL.
        **kwargs: Additional config passed to LLMConfig.

    Returns:
        Configured LLMAdapter instance.

    Raises:
        ValueError: If the provider is not supported.

    Example:
        >>> llm = create_llm(
        ...     provider="claude",
        ...     model="claude-sonnet-5-20251001",
        ...     api_key="sk-ant-...",
        ... )
        >>> response = await llm.chat([Message(role="user", content="...")])
    """
    provider_key = provider.lower()

    if provider_key not in _PROVIDERS:
        supported = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unsupported provider: '{provider}'. "
            f"Supported providers: {supported}"
        )

    config = LLMConfig(
        model=model,
        api_key=api_key,
        api_base=api_base,
        **kwargs
    )

    adapter_cls = _PROVIDERS[provider_key]
    return adapter_cls(config)


def register_provider(name: str, adapter_cls: type) -> None:
    """Register a custom LLM adapter.

    Args:
        name: Provider name (e.g., 'gemini', 'qwen').
        adapter_cls: Adapter class (must inherit LLMAdapter).

    Example:
        >>> from scope_code.llm import register_provider
        >>> from my_adapters import GeminiAdapter
        >>> register_provider("gemini", GeminiAdapter)
    """
    if not issubclass(adapter_cls, LLMAdapter):
        raise TypeError(
            f"Adapter must be a subclass of LLMAdapter, "
            f"got {adapter_cls.__name__}"
        )
    _PROVIDERS[name.lower()] = adapter_cls


def list_providers() -> list:
    """List all registered provider names."""
    return sorted(_PROVIDERS.keys())
