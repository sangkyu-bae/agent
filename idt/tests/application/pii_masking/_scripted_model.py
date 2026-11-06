"""그래프 테스트용 스크립트 채팅 모델 (명시적 fake).

받은 메시지를 기록하고 미리 정한 응답을 순서대로 돌려준다. 스트리밍 시 본문을
3자씩 쪼개 내보내 placeholder가 청크 경계에 걸리는 상황을 재현한다.
"""

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    script: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    fail_first: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen.append(list(messages))
        if self.fail_first > 0:
            self.fail_first -= 1
            raise RuntimeError("transient failure")
        return self.script.pop(0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._next(messages)
        if message.tool_calls:
            chunks = [
                {
                    "name": c["name"],
                    "args": json.dumps(c["args"], ensure_ascii=False),
                    "id": c["id"],
                    "index": i,
                    "type": "tool_call_chunk",
                }
                for i, c in enumerate(message.tool_calls)
            ]
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_call_chunks=chunks)
            )
            return
        text = message.content
        for start in range(0, len(text), 3):
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=text[start : start + 3])
            )


def sent_text(model: ScriptedChatModel) -> str:
    """모델에 실제로 전송된 모든 메시지 직렬화 (원본 PII 부재 단언용)."""
    parts = []
    for messages in model.seen:
        for message in messages:
            parts.append(repr(message.content))
            parts.append(repr(getattr(message, "tool_calls", None)))
            parts.append(repr(message.additional_kwargs))
    return "\n".join(parts)
