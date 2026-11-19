from abc import ABC, abstractmethod

from langchain_openai import ChatOpenAI

from src.config import settings
from src.domain.llm.message_content import coerce_message_text


class LLMAdapter(ABC):
    @abstractmethod
    async def generate(self, message: str) -> str:
        pass


class OpenAIAdapter(LLMAdapter):
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
        )

    async def generate(self, message: str) -> str:
        response = await self._llm.ainvoke(message)
        return coerce_message_text(response.content)
