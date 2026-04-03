"""OpenAI LLM Provider implementation."""
import asyncio
import json
from typing import List, Type

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.compressor.value_objects.llm_config import LLMConfig


class OpenAIProvider(LLMProviderInterface):
    """OpenAI implementation of LLMProviderInterface.

    Uses AsyncOpenAI client for non-blocking API calls.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize OpenAI provider with configuration.

        Args:
            config: LLM configuration including model and API key.
        """
        self._config = config
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._model = config.model_name

    async def generate(self, prompt: str) -> str:
        """Generate a text response for a single prompt.

        Args:
            prompt: The input prompt to send to OpenAI.

        Returns:
            The generated text response.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        return response.choices[0].message.content

    async def generate_batch(self, prompts: List[str]) -> List[str]:
        """Generate text responses for multiple prompts using asyncio.gather.

        Args:
            prompts: List of input prompts to send to OpenAI.

        Returns:
            List of generated text responses in the same order as prompts.
        """
        if not prompts:
            return []

        tasks = [self.generate(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def generate_structured(
        self, prompt: str, schema: Type[BaseModel]
    ) -> BaseModel:
        """Generate a structured response matching a Pydantic schema.

        Uses OpenAI's JSON mode to ensure valid JSON output.

        Args:
            prompt: The input prompt to send to OpenAI.
            schema: The Pydantic model class defining the expected output structure.

        Returns:
            An instance of the schema populated with the LLM's response.
        """
        schema_json = schema.model_json_schema()
        enhanced_prompt = (
            f"{prompt}\n\n"
            f"Respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}"
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": enhanced_prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return schema.model_validate_json(content)

    def get_provider_name(self) -> str:
        """Get the provider name.

        Returns:
            Always returns "openai".
        """
        return "openai"

    def get_model_name(self) -> str:
        """Get the model name from configuration.

        Returns:
            The model identifier (e.g., "gpt-4o-mini").
        """
        return self._model
