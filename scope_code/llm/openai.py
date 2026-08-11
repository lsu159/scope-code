"""OpenAI adapter — Chat Completions API via httpx."""

import json
from typing import List, Dict, Any

import httpx

from .base import LLMAdapter, LLMConfig, Message


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI GPT models via the Chat Completions API.

    Uses the Chat API directly via httpx to avoid SDK dependency.
    API docs: https://platform.openai.com/docs/api-reference/chat
    """

    DEFAULT_API_BASE = "https://api.openai.com/v1"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._api_base = config.api_base or self.DEFAULT_API_BASE
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send a chat request to OpenAI."""
        api_messages = self._convert_messages(messages)

        body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": api_messages,
        }

        response = await self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()

        return data["choices"][0]["message"]["content"]

    async def structured_output(
        self,
        messages: List[Message],
        output_schema: dict,
        **kwargs
    ) -> dict:
        """Request structured JSON output from OpenAI.

        Uses OpenAI's JSON mode / response_format for structured output.
        """
        api_messages = self._convert_messages(messages)

        # Add schema instruction to the last user message or as system
        schema_json = json.dumps(output_schema, indent=2)
        schema_instruction = (
            f"You must respond with ONLY a valid JSON object "
            f"that conforms to this schema:\n{schema_json}\n"
            f"Do not include markdown formatting or explanation."
        )

        # Append instruction to the last user message
        api_messages[-1]["content"] += f"\n\n{schema_instruction}"

        body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": api_messages,
            "response_format": {"type": "json_object"},
        }

        response = await self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()

        text = data["choices"][0]["message"]["content"]
        return json.loads(text)

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """Convert Scope Code messages to OpenAI format.

        Wraps system messages with framework instructions.
        """
        result = []
        for msg in messages:
            content = msg.content
            if msg.role == "system":
                content = self._build_system_prompt(content)
            result.append({"role": msg.role, "content": content})
        return result

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
