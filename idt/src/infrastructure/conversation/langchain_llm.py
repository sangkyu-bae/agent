"""LangChain 기반 대화 LLM 구현."""
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.application.conversation.interfaces import ConversationLLMInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _to_lc_message(msg: dict):
    role = msg.get("role", "user")
    content = msg.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


class LangChainConversationLLM(ConversationLLMInterface):
    """ChatOpenAI를 활용한 대화 LLM."""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        logger: LoggerInterface,
    ) -> None:
        self._llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0)
        self._logger = logger

    async def generate(
        self,
        messages: list[dict],
        request_id: str,
    ) -> str:
        self._logger.info(
            "LangChainConversationLLM generate started",
            request_id=request_id,
            message_count=len(messages),
        )
        try:
            lc_messages = [_to_lc_message(m) for m in messages]
            response = await self._llm.ainvoke(lc_messages)
            answer = response.content
            self._logger.info(
                "LangChainConversationLLM generate completed",
                request_id=request_id,
            )
            return answer
        except Exception as e:
            self._logger.error(
                "LangChainConversationLLM generate failed",
                exception=e,
                request_id=request_id,
            )
            raise
