"""빌더 에이전트 생성 어댑터 (application.ports.AgentCreator 구현).

Design Ref: stock-analysis-agents §5.1 bootstrap,
Plan Q6. 플랫폼 `CreateAgentUseCase` 를 그대로 쓴다 —
지침은 넘긴 그대로 저장된다(LLM 재생성 없음,
create_agent_use_case Step "system_prompt").
- 공개 범위 private, 모델은 플랫폼 기본(None).
빌트인 도구는 관리자 카탈로그 설정대로 붙는다
- 실패는 (None, 사유) 로 돌려준다 — 한 역할 실패가 나머지 생성을 막지 않는다
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_USER_REQUEST = "시장 분석 모듈 기본 에이전트 — {name}"


class PlatformAgentCreator:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        create_uc_builder: Callable[[Any], Any],
        viewer_role: str,
        logger: LoggerInterface,
    ) -> None:
        self._sf = session_factory
        self._builder = create_uc_builder
        self._viewer_role = viewer_role
        self._logger = logger

    async def create(
        self,
        *,
        name: str,
        system_prompt: str,
        tool_ids: list[str],
        owner_user_id: str,
        token_limit: int,
        request_id: str,
    ) -> tuple[str | None, str | None]:
        request = CreateAgentRequest(
            user_request=_USER_REQUEST.format(name=name)[:1000],
            name=name,
            user_id=owner_user_id,
            llm_model_id=None,
            visibility="private",
            token_limit=token_limit,
            tool_ids=list(tool_ids) or None,
            system_prompt=system_prompt,
        )
        try:
            async with self._sf() as session:
                async with session.begin():
                    response = await self._builder(session).execute(
                        request, request_id, viewer_role=self._viewer_role
                    )
        except Exception as e:  # noqa: BLE001 — 역할 하나의 실패는 결과로 돌려준다
            self._logger.warning(
                "market_analysis agent create failed",
                exception=e,
                request_id=request_id,
                name=name,
            )
            return None, str(e)[:300]
        return str(response.agent_id), None
