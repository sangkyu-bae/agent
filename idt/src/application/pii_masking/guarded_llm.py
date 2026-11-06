"""GuardedLlm: 미들웨어를 거치지 않는 직접 LLM 호출용 프록시.

Design Ref: pii-masking-integration §4.4 (FR-05, FR-06) — supervisor·final_answer·
파이프라인·보조 LLM은 `llm.ainvoke`를 직접 부른다. 진입점(compile, UtilityLLMProvider)
에서 이 프록시로 감싸면 하위 노드를 고치지 않아도 같은 경계가 적용된다.

- `prompt | guarded` 체인이 동작하도록 Runnable을 상속한다.
- `with_structured_output`·`bind_tools`·`bind`는 결과를 다시 감싼다. 감싸지 않으면
  구조화 출력 호출이 경계를 우회한다.
- create_agent에는 넘기지 않는다. 런타임이 raw 모델에 bind_tools를 호출하며,
  그 경로는 PiiMaskingMiddleware가 맡는다.
- scope가 None이면 호출마다 새 scope를 쓴다. 앱 싱글턴 어댑터는 런을 모르지만
  입력 전체에 원본이 있으므로 호출 단위 vault로도 일관성이 유지된다.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    convert_to_messages,
)
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable

from src.application.pii_masking.message_masker import PiiMessageMasker
from src.domain.pii_masking.schemas import PiiRunScope


class GuardedLlm(Runnable):
    """내부 모델 앞뒤에서 마스킹·원복만 하는 얇은 프록시."""

    def __init__(
        self,
        inner: Any,
        masker: PiiMessageMasker,
        scope: PiiRunScope | None = None,
    ) -> None:
        self._inner = inner
        self._masker = masker
        self._scope = scope

    @property
    def inner(self) -> Any:
        return self._inner

    @property
    def scope(self) -> PiiRunScope | None:
        return self._scope

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        scope = self._scope or self._masker.new_scope()
        output = self._inner.invoke(self._mask(input, scope), config, **kwargs)
        return self._masker.restore_output(output, scope)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        scope = self._scope or self._masker.new_scope()
        output = await self._inner.ainvoke(self._mask(input, scope), config, **kwargs)
        return self._masker.restore_output(output, scope)

    def with_structured_output(self, *args: Any, **kwargs: Any) -> GuardedLlm:
        return self._rewrap(self._inner.with_structured_output(*args, **kwargs))

    def bind_tools(self, *args: Any, **kwargs: Any) -> GuardedLlm:
        return self._rewrap(self._inner.bind_tools(*args, **kwargs))

    def bind(self, **kwargs: Any) -> GuardedLlm:
        return self._rewrap(self._inner.bind(**kwargs))

    def __getattr__(self, name: str) -> Any:
        # __init__ 이전이나 dunder 조회에서 재귀하지 않도록 직접 꺼낸다.
        if name.startswith("__"):
            raise AttributeError(name)
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)

    def _rewrap(self, inner: Any) -> GuardedLlm:
        return GuardedLlm(inner, self._masker, self._scope)

    def _mask(self, input: Any, scope: PiiRunScope) -> list[BaseMessage]:
        messages = _to_messages(input)
        first = messages[0] if messages else None
        system = first if isinstance(first, SystemMessage) else None
        rest = messages[1:] if system is not None else messages
        body, head = self._masker.mask_request(rest, scope, system=system)
        return ([head] if head is not None else []) + body


def _to_messages(input: Any) -> list[BaseMessage]:
    """모델 입력 형식을 메시지 목록으로 정규화한다. 모르는 형식은 거부한다."""
    if isinstance(input, PromptValue):
        return input.to_messages()
    if isinstance(input, str):
        return [HumanMessage(content=input)]
    if isinstance(input, (list, tuple)):
        return convert_to_messages(input)
    raise TypeError(f"GuardedLlm: unsupported input type {type(input).__name__}")
