"""LangChain 기반 대화 히스토리 요약기 구현."""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.application.conversation.interfaces import ConversationSummarizerInterface
from src.domain.conversation.entities import ConversationMessage
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SYSTEM_PROMPT = (
    "당신은 대화 내용을 사실 중심으로 요약하는 전문가입니다.\n"
    "요약 규칙:\n"
    "- 결정사항, 사용자 의도, 중요한 제약을 포함\n"
    "- 질문/답변 형식 금지\n"
    "- 간결하고 명확한 문장으로 작성\n"
    "아래 대화를 요약하세요."
)


class LangChainSummarizer(ConversationSummarizerInterface):
    """ChatOpenAI를 활용한 대화 히스토리 요약기."""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        logger: LoggerInterface,
    ) -> None:
        self._llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0)
        self._logger = logger

    async def summarize(
        self,
        messages: list[ConversationMessage],
        request_id: str,
    ) -> str:
        self._logger.info(
            "LangChainSummarizer started",
            request_id=request_id,
            message_count=len(messages),
        )
        try:
            conversation_text = "\n".join(
                f"[{msg.role.value}] {msg.content}" for msg in messages
            )
            lc_messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=conversation_text),
            ]
            response = await self._llm.ainvoke(lc_messages)
            summary = response.content
            self._logger.info(
                "LangChainSummarizer completed",
                request_id=request_id,
            )
            return summary
        except Exception as e:
            self._logger.error(
                "LangChainSummarizer failed",
                exception=e,
                request_id=request_id,
            )
            raise
