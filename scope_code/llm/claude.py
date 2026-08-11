"""Claude adapter — Anthropic Messages API via httpx."""

import json
from typing import List, Dict, Any

import httpx

from .base import LLMAdapter, LLMConfig, Message


class ClaudeAdapter(LLMAdapter):
    """Adapter for Anthropic Claude models via the Messages API.

    Uses the Messages API directly via httpx to avoid SDK dependency.
    API docs: https://docs.anthropic.com/en/api/messages
    """

    DEFAULT_API_BASE = "https://api.anthropic.com/v1"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._api_base = config.api_base or self.DEFAULT_API_BASE
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": self.ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    @property
    def provider_name(self) -> str:
        return "claude"

    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send a chat request to Claude."""
        system_prompts, user_messages = self._split_messages(messages)

        body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": user_messages,
        }

        if system_prompts:
            body["system"] = self._build_system_prompt(
                "\n".join(system_prompts)
            )

        response = await self._client.post("/messages", json=body)
        response.raise_for_status()
        data = response.json()

        # Extract text from the first content block
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]

        return ""

    async def structured_output(
        self,
        messages: List[Message],
        output_schema: dict,
        **kwargs
    ) -> dict:
        """Request structured JSON output from Claude.

        Uses Claude's tool_use feature with a constrained output tool.
        """
        system_prompts, user_messages = self._split_messages(messages)

        # Add JSON output instruction to system prompt
        schema_json = json.dumps(output_schema, indent=2)
        schema_instruction = (
            f"IMPORTANT: You must respond with ONLY a valid JSON object "
            f"that conforms to this schema:\n```json\n{schema_json}\n```\n"
            f"Do not include any other text, markdown formatting, or "
            f"explanation outside the JSON."
        )
        all_system = "\n".join(system_prompts + [schema_instruction])

        body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": user_messages,
            "system": self._build_system_prompt(all_system),
        }

        response = await self._client.post("/messages", json=body)
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        return self._parse_json(text, output_schema)

    def _split_messages(
        self, messages: List[Message]
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        """Split messages into system prompts and user/assistant messages.

        Claude API uses a separate 'system' field, not system messages.
        """
        system_prompts = []
        user_messages = []

        for msg in messages:
            if msg.role == "system":
                system_prompts.append(msg.content)
            else:
                user_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return system_prompts, user_messages

    def _parse_json(self, text: str, schema: dict) -> dict:
        """Extract and parse JSON from LLM text response."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract from markdown code blocks
        import re
        json_match = re.search(
            r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object boundaries
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to parse JSON from response: {text[:200]}...")

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
