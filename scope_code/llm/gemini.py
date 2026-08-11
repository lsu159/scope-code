"""Google Gemini adapter — Generative Language API via httpx.

API docs: https://ai.google.dev/api/generate-content
"""

import json
from typing import List, Dict, Any

import httpx

from .base import LLMAdapter, LLMConfig, Message


class GeminiAdapter(LLMAdapter):
    """Adapter for Google Gemini models via the Generative Language API.

    Uses the generateContent endpoint directly via httpx.
    """

    DEFAULT_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._api_base = config.api_base or self.DEFAULT_API_BASE
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        self._api_key = config.api_key

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send a chat request to Gemini."""
        model = kwargs.get("model", self.config.model)
        system_instructions, contents = self._convert_messages(messages)

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get(
                    "max_tokens", self.config.max_tokens
                ),
                "temperature": kwargs.get(
                    "temperature", self.config.temperature
                ),
            },
        }

        if system_instructions:
            body["systemInstruction"] = {
                "parts": [{"text": system_instructions}]
            }

        response = await self._client.post(
            f"/models/{model}:generateContent",
            params={"key": self._api_key},
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        return self._extract_text(data)

    async def structured_output(
        self,
        messages: List[Message],
        output_schema: dict,
        **kwargs
    ) -> dict:
        """Request structured JSON output from Gemini.

        Uses Gemini's response_mime_type and response_schema for
        native structured output support.
        """
        model = kwargs.get("model", self.config.model)
        system_instructions, contents = self._convert_messages(messages)

        # Add JSON instruction to system prompt
        schema_json = json.dumps(output_schema, indent=2)
        json_instruction = (
            f"You must respond with a valid JSON object matching "
            f"this schema:\n{schema_json}"
        )
        if system_instructions:
            system_instructions = (
                self._build_system_prompt(system_instructions)
                + "\n\n" + json_instruction
            )
        else:
            system_instructions = (
                self._build_system_prompt("") + "\n\n" + json_instruction
            )

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get(
                    "max_tokens", self.config.max_tokens
                ),
                "temperature": kwargs.get(
                    "temperature", self.config.temperature
                ),
                "response_mime_type": "application/json",
            },
        }

        if system_instructions:
            body["systemInstruction"] = {
                "parts": [{"text": system_instructions}]
            }

        response = await self._client.post(
            f"/models/{model}:generateContent",
            params={"key": self._api_key},
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        text = self._extract_text(data)
        return json.loads(text)

    def _convert_messages(
        self, messages: List[Message]
    ) -> tuple[str, List[Dict]]:
        """Convert Scope Code messages to Gemini format.

        Returns:
            (system_instructions, contents)
        """
        system_parts = []
        contents = []

        for i, msg in enumerate(messages):
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg.content}],
                })
            elif msg.role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": msg.content}],
                })

        system_text = "\n\n".join(system_parts)
        if system_text:
            system_text = self._build_system_prompt(system_text)

        return system_text, contents

    def _extract_text(self, data: Dict) -> str:
        """Extract text from a Gemini API response."""
        candidates = data.get("candidates", [])
        if not candidates:
            # Check for prompt feedback (safety blocks)
            feedback = data.get("promptFeedback", {})
            if feedback.get("blockReason"):
                raise ValueError(
                    f"Gemini blocked response: "
                    f"{feedback.get('blockReason')}"
                )
            raise ValueError("Gemini returned no candidates.")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "")

        if finish_reason and finish_reason != "STOP":
            # Safety or other issue — still try to get text
            pass

        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_parts = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])

        return "\n".join(text_parts)

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
