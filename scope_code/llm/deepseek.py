"""DeepSeek adapter — OpenAI-compatible API via httpx.

DeepSeek API is compatible with the OpenAI chat completions format.
API docs: https://platform.deepseek.com/api-docs

Default model: deepseek-chat (DeepSeek-V3)
Reasoning model: deepseek-reasoner (DeepSeek-R1)
"""

from .openai import OpenAIAdapter
from .base import LLMConfig


class DeepSeekAdapter(OpenAIAdapter):
    """Adapter for DeepSeek models via the OpenAI-compatible API.

    DeepSeek's API is fully compatible with the OpenAI Chat Completions
    format, so we inherit from OpenAIAdapter and just override the defaults.

    Key differences from OpenAI:
        - Default base URL: https://api.deepseek.com
        - Default model: deepseek-chat
        - No support for response_format json_object (use prompt-based JSON)
    """

    DEFAULT_API_BASE = "https://api.deepseek.com/v1"

    def __init__(self, config: LLMConfig):
        # Override API base if not explicitly set
        if config.api_base is None:
            config.api_base = self.DEFAULT_API_BASE
        if not config.model:
            config.model = "deepseek-chat"
        super().__init__(config)

    @property
    def provider_name(self) -> str:
        return "deepseek"

    async def structured_output(
        self, messages, output_schema: dict, **kwargs
    ) -> dict:
        """Request structured JSON from DeepSeek.

        DeepSeek doesn't support response_format json_object natively,
        so we use prompt-based JSON instruction instead of the API flag.
        """
        import json
        # Override: prompt-based JSON instead of response_format

        api_messages = []
        for msg in messages:
            content = msg.content
            if msg.role == "system":
                content = self._build_system_prompt(content)
            api_messages.append({"role": msg.role, "content": content})

        schema_json = json.dumps(output_schema, indent=2)
        schema_instruction = (
            f"\n\nYou must respond with ONLY a valid JSON object "
            f"that conforms to this schema. "
            f"Do not include markdown formatting or explanation:\n"
            f"```json\n{schema_json}\n```\n"
            f"Output ONLY the JSON, nothing else."
        )
        api_messages[-1]["content"] += schema_instruction

        body = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": api_messages,
        }

        response = await self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()

        text = data["choices"][0]["message"]["content"]
        return json.loads(text)
