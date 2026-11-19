"""강제 tool_choice 를 거부하는 Claude 모델용 ChatAnthropic.

claude-agent-e2e-fixes Design §5.2.

LangChain ``with_structured_output`` 기본(method="function_calling")은 Anthropic 에
``tool_choice: {type: "tool"}`` 를 보낸다. Opus 5.5 등은 이를 400 으로 거부하므로
기본 method 만 "json_schema"(Anthropic 구조화 출력)로 바꾼다. 호출부가 method 를
명시하면 존중한다. 그 외 동작은 ChatAnthropic 과 같다.

LLMFactory 가 domain 정책(anthropic_supports_forced_tool_choice)으로 선택해 생성한다.
호출 지점(41곳)과 PII 프록시(GuardedLlm — inner 위임)는 수정하지 않는다.
"""
from typing import Any

from langchain_anthropic import ChatAnthropic


class JsonSchemaStructuredChatAnthropic(ChatAnthropic):
    """with_structured_output 의 기본 method 가 json_schema 인 ChatAnthropic."""

    def with_structured_output(
        self,
        schema: Any,
        *,
        include_raw: bool = False,
        method: str = "json_schema",
        **kwargs: Any,
    ) -> Any:
        return super().with_structured_output(
            schema, include_raw=include_raw, method=method, **kwargs
        )
