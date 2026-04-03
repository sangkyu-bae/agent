from abc import ABC, abstractmethod

from langchain_openai import ChatOpenAI

from src.config import settings


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
        return str(response.content)
