"""MiddlewareProvider: 실행 시 조립 진입점 (D6).

compile/stream당 1회 prepare()로 카탈로그 조회·병합·폴백 해석을 마치고,
워커마다 plan.instantiate()로 새 인스턴스 목록을 만든다 (상태 공유 금지).
"""
from dataclasses import dataclass

from src.application.middleware.middleware_builder import MiddlewareBuilder
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    AppliedMiddleware,
    MiddlewareType,
)
from src.domain.middleware.interfaces import (
    AgentMiddlewareRepositoryInterface,
    MiddlewareCatalogRepositoryInterface,
)
from src.domain.middleware.policies import MiddlewareMergePolicy


@dataclass
class MiddlewarePlan:
    """prepare() 결과 — instantiate()가 워커별 신규 인스턴스 목록 생성."""

    applied: list[AppliedMiddleware]
    fallback_models: list
    builder: MiddlewareBuilder
    request_id: str

    def instantiate(self) -> list:
        """공통(워커 무관) 미들웨어 인스턴스 목록.

        approval-gate Design §2.1: 승인 게이트는 "이 워커의 도구가 승인
        대상인가" 를 알아야 하므로 공통 경로에서 제외하고, 컴파일러가
        워커마다 MiddlewareBuilder.build_approval_gate 로 조립한다.
        여기 남겨 두면 도구를 모른 채 모든 워커에 붙어 무해한 워커까지 막는다.
        게이트 적용 여부·설정은 `applied` 를 직접 읽어 판단한다.
        """
        common = [
            a
            for a in self.applied
            if a.middleware_type is not MiddlewareType.APPROVAL_GATE
        ]
        if not common:
            return []
        return self.builder.build(
            common, self.request_id, fallback_models=self.fallback_models
        )


class MiddlewareProvider:
    def __init__(
        self,
        catalog_repo: MiddlewareCatalogRepositoryInterface,
        agent_middleware_repo: AgentMiddlewareRepositoryInterface | None,
        llm_model_repo: LlmModelRepositoryInterface,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._catalog_repo = catalog_repo
        self._agent_middleware_repo = agent_middleware_repo
        self._llm_model_repo = llm_model_repo
        self._llm_factory = llm_factory
        self._logger = logger
        self._builder = MiddlewareBuilder(logger=logger)

    async def prepare(
        self,
        agent_id: str | None,
        request_id: str,
        *,
        default_builtin: bool = True,
    ) -> MiddlewarePlan:
        """적용 플랜 준비 (조회·병합·폴백 해석 — 호출당 1회).

        agent_id가 None일 때:
        - default_builtin=True (General Chat, D7): 빌트인 ∪ enforced 전부 적용.
        - default_builtin=False (컴파일러의 agent_id 미상 경로): enforced만 —
          스냅샷을 알 수 없는 상태에서 사용자 opt-out을 무시하지 않기 위함.
        """
        catalog = await self._catalog_repo.list_all(request_id)
        # approval-gate Design §3.4: merge 가 record.config 오버라이드를 읽으므로
        # 타입 목록이 아니라 record 를 그대로 넘긴다. 에이전트 스냅샷이 없는
        # 경로는 빈 config 의 가상 record 로 변환해 기존 동작을 보존한다.
        if agent_id is not None and self._agent_middleware_repo is not None:
            records = await self._agent_middleware_repo.list_by_agent(
                agent_id, request_id
            )
        elif default_builtin:
            records = [
                AgentMiddlewareRecord(
                    agent_id=agent_id or "",
                    middleware_type=e.middleware_type.value,
                    sort_order=e.sort_order,
                )
                for e in catalog
                if e.is_builtin and e.is_active
            ]
        else:
            records = []

        applied = MiddlewareMergePolicy.merge(records, catalog)
        fallback_models = await self._resolve_fallback_models(applied, request_id)

        # FR-12: 적용 목록 관측 로그 (request_id 포함)
        self._logger.info(
            "Middleware plan prepared",
            request_id=request_id,
            agent_id=agent_id,
            middleware_types=[a.middleware_type.value for a in applied],
        )
        return MiddlewarePlan(
            applied=applied,
            fallback_models=fallback_models,
            builder=self._builder,
            request_id=request_id,
        )

    async def _resolve_fallback_models(
        self, applied: list[AppliedMiddleware], request_id: str
    ) -> list:
        """model_fallback의 모델명 → BaseChatModel 해석 (D8).

        미등록/비활성 모델명은 경고 후 제외 — 문자열을 langchain에 직접
        넘기지 않는다 (커스텀 base_url/ollama 모델은 init_chat_model 미해석).
        """
        fallback = next(
            (
                a
                for a in applied
                if a.middleware_type is MiddlewareType.MODEL_FALLBACK
            ),
            None,
        )
        if fallback is None:
            return []
        names = fallback.config.get("fallback_models", [])
        if not names:
            return []
        active = await self._llm_model_repo.list_active(request_id)
        by_name = {m.model_name: m for m in active}
        resolved = []
        for name in names:
            model = by_name.get(name)
            if model is None:
                self._logger.warning(
                    "Fallback model unresolved — skipped",
                    request_id=request_id,
                    model_name=name,
                )
                continue
            resolved.append(self._llm_factory.create(model, 0.0))
        return resolved
