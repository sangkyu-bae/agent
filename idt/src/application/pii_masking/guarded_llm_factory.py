"""PiiGuardedLLMFactory: 앱 싱글턴 보조 LLM 소비자용 팩토리 래퍼.

Design Ref: pii-masking-integration §4.4, §11.1 (FR-06) — UtilityLLMProvider·차트 LLM·
도구 선별기는 런을 모르는 앱 싱글턴이다. 이들에 넘기는 팩토리를 감싸면 만들어지는
모델이 모두 GuardedLlm(scope=None, 호출 단위 vault)이 된다.

- masker 는 호출 시점에 조회한다(getter). DI 조립 순서와 무관하고, 해제(None)면
  원본 모델을 그대로 돌려준다.
- WorkflowCompiler 에는 넘기지 않는다. 컴파일러는 raw 모델이 필요하고(create_agent),
  스스로 런 scope 로 감싼다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.application.pii_masking.guarded_llm import GuardedLlm
from src.application.pii_masking.message_masker import PiiMessageMasker
from src.domain.llm.interfaces import LLMFactoryInterface

MaskerGetter = Callable[[], PiiMessageMasker | None]


class PiiGuardedLLMFactory(LLMFactoryInterface):
    def __init__(self, inner: LLMFactoryInterface, masker_getter: MaskerGetter) -> None:
        self._inner = inner
        self._masker_getter = masker_getter

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return self.guard(self._inner.create(*args, **kwargs))

    def guard(self, llm: Any) -> Any:
        """팩토리 밖에서 만든 모델(요약기 등)도 같은 규칙으로 감싼다."""
        if isinstance(llm, GuardedLlm):
            return llm
        masker = self._masker_getter()
        if masker is None:
            return llm
        return GuardedLlm(llm, masker)
