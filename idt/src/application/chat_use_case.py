from src.infrastructure.llm_adapter import LLMAdapter


class ChatUseCase:
    def __init__(self, llm_adapter: LLMAdapter) -> None:
        self._llm_adapter = llm_adapter

    async def execute(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> str:
        return await self._llm_adapter.generate(message)
