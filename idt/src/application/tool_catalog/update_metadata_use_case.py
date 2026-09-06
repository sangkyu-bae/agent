"""UpdateToolMetadataUseCase: 도구 분류·호출 상한 지정 (관리자 전용).

Design Ref: mcp-tool-category-routing §4.2 (FR-02·FR-13) / §5 D-04

이 사이클은 카테고리를 자동 추론하지 않는다. 동기화는 값을 채우지 않고
(D-02 보존 계약), 실제 동작 변화는 관리자가 여기서 지정한 도구에서만 일어난다
— category NULL = 이 사이클 이전과 동일 경로(FR-14)를 지키기 위한 설계다.

검증은 도메인(ToolCategoryPolicy)이 하고 유스케이스는 '무엇을 갱신할지'만
정한다. 부분 갱신은 UNSET 센티널로 표현한다 — 명시적 None('미분류로
되돌리기')과 인자 생략('변경 없음')이 다른 의미이기 때문.
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import (
    UNSET,
    ToolCatalogRepositoryInterface,
)
from src.domain.tool_catalog.policies import ToolCategoryPolicy


class UpdateToolMetadataUseCase:
    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        tool_id: str,
        request_id: str,
        *,
        category: str | None = UNSET,
        max_tool_calls: int | None = UNSET,
    ) -> ToolCatalogEntry:
        """분류·호출 상한을 부분 갱신한다.

        Args:
            tool_id: 카탈로그 tool_id
            request_id: 추적 id
            category: 지정할 분류. 생략 시 미변경, None이면 미분류로 되돌림
            max_tool_calls: 호출 상한. 생략 시 미변경, None이면 기본값 사용

        Returns:
            갱신된 카탈로그 엔트리

        Raises:
            ValueError: 도메인 정책 위반 (허용값 밖 / collect 지정 불가 도구)
            LookupError: tool_id에 해당하는 도구가 없음
        """
        self._logger.info(
            "UpdateToolMetadataUseCase start",
            request_id=request_id, tool_id=tool_id,
        )
        try:
            # 값 자체가 틀렸으면 존재 확인보다 먼저 거부한다 — 불필요한 조회 방지.
            if category is not UNSET:
                ToolCategoryPolicy.validate(category)
            if max_tool_calls is not UNSET:
                ToolCategoryPolicy.validate_tool_call_limit(max_tool_calls)

            existing = await self._repository.find_by_tool_id(tool_id, request_id)
            if existing is None:
                raise LookupError(f"Unknown catalog tool_id: {tool_id!r}")

            # D-04: collect 적격성은 대상 도구를 알아야 판정할 수 있다.
            if category is not UNSET:
                ToolCategoryPolicy.assert_assignable(category, existing.tool_id)

            updated = await self._repository.update_metadata(
                tool_id, request_id,
                category=category, max_tool_calls=max_tool_calls,
            )
            if updated is None:
                # 조회 직후 삭제된 경쟁 상황 — 404로 수렴시킨다.
                raise LookupError(f"Unknown catalog tool_id: {tool_id!r}")

            self._logger.info(
                "UpdateToolMetadataUseCase done",
                request_id=request_id, tool_id=tool_id,
                category=updated.category, max_tool_calls=updated.max_tool_calls,
            )
            return updated
        except (ValueError, LookupError):
            # 도메인 판정·미존재는 호출자(라우터)가 상태코드로 번역한다.
            raise
        except Exception as e:
            self._logger.error(
                "UpdateToolMetadataUseCase failed",
                exception=e, request_id=request_id, tool_id=tool_id,
            )
            raise
