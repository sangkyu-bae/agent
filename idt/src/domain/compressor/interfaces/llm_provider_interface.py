"""LLMProviderInterface for abstracting LLM providers."""
from abc import ABC, abstractmethod
from typing import List, Type

from pydantic import BaseModel


class LLMProviderInterface(ABC):
    """Abstract interface for LLM providers.

    This interface defines the contract for LLM providers that can generate
    text responses, batch responses, and structured outputs.
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate a text response for a single prompt.

        Args:
            prompt: The input prompt to send to the LLM.

        Returns:
            The generated text response.
        """
        pass

    @abstractmethod
    async def generate_batch(self, prompts: List[str]) -> List[str]:
        """Generate text responses for multiple prompts.

        Args:
            prompts: List of input prompts to send to the LLM.

        Returns:
            List of generated text responses in the same order as prompts.
        """
        pass

    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema: Type[BaseModel]
    ) -> BaseModel:
        """Generate a structured response matching a Pydantic schema.

        Args:
            prompt: The input prompt to send to the LLM.
            schema: The Pydantic model class defining the expected output structure.

        Returns:
            An instance of the schema populated with the LLM's response.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of the LLM provider.

        Returns:
            The provider name (e.g., "openai", "anthropic").
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the model being used.

        Returns:
            The model identifier (e.g., "gpt-4o-mini", "claude-3-sonnet").
        """
        pass
