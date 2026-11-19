"""UtilityLLMProviderPort 테스트 대역.

get()은 요청한 temperature를 기록하고, ainvoke 가능한 LLM(Mock)을 돌려준다.
available=False면 get()이 None을 돌려준다 (모델 해석 실패 경로).
"""
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock


class FakeUtilityLLM:
    def __init__(self, *contents: Any, available: bool = True) -> None:
        self.llm = Mock()
        responses = [SimpleNamespace(content=c) for c in contents or ("",)]
        if len(responses) == 1:
            self.llm.ainvoke = AsyncMock(return_value=responses[0])
        else:
            self.llm.ainvoke = AsyncMock(side_effect=responses)
        self.temperatures: list[float] = []
        self._available = available

    async def get(self, temperature: float = 0.0):
        self.temperatures.append(temperature)
        return self.llm if self._available else None

    async def invalidate(self) -> None:
        return None

    def prompt(self, call: int = -1) -> str:
        """ainvoke에 넘긴 마지막 user 메시지 본문."""
        messages = self.llm.ainvoke.call_args_list[call].args[0]
        return messages[-1]["content"]
