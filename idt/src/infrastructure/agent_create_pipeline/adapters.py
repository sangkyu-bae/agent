"""파이프라인용 도구 어댑터 2종 — Design §2.3 / §6.1.

- CatalogCandidateReader: tool_catalog 전체 활성 → ToolCandidate 후보.
- NullToolSelector: 셀렉터(LLM) 미구성 시의 강하 구현 — 파이프라인이
  degraded 로 진행할 수 있게 항상 fallback 을 돌려준다.
"""
from collections.abc import Sequence

from src.domain.agent_create_pipeline.interfaces import ToolCandidateReaderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface
from src.domain.tool_selection.interfaces.tool_selector_port import ToolSelectorPort
from src.domain.tool_selection.schemas import (
    SelectionResult,
    ToolCandidate,
    ToolSource,
)

_REQUEST_ID = "agent-pipeline-candidates"


class CatalogCandidateReader(ToolCandidateReaderPort):
    """tool_catalog 활성 전체를 셀렉터 후보로 투영한다.

    tool_id 는 카탈로그 표기를 그대로 쓴다 — 이중 네임스페이스 변환은
    저장·런타임 경계의 책임이며 여기서 하지 않는다 (도구 규칙).
    """

    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def list_active(self) -> tuple[ToolCandidate, ...]:
        """포트 계약: 예외 금지 — 실패는 빈 튜플 + warning (degraded 강하)."""
        try:
            entries = await self._repository.list_active(_REQUEST_ID)
        except Exception as e:
            self._logger.warning(
                "pipeline candidate load failed — empty candidates",
                exception=e,
            )
            return ()
        return tuple(
            ToolCandidate(
                tool_id=entry.tool_id,
                name=entry.name,
                description=entry.description or "",
                source=_to_source(entry.source),
                server_name=None,  # 사람이 읽는 서버명은 런타임에 없다 (위키)
            )
            for entry in entries
        )


class NullToolSelector(ToolSelectorPort):
    """셀렉터 미구성 시 강하 구현 — LLM 호출 없이 required 만 통과.

    ToolSelectorPort 계약(예외 금지·required 보존·축소만)을 그대로 지키므로
    파이프라인은 구성 여부를 모른 채 steps.tools=degraded 로 관측한다.
    """

    async def select(
        self,
        query: str,
        candidates: Sequence[ToolCandidate],
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> SelectionResult:
        deduped = tuple(dict.fromkeys(required_ids))
        return SelectionResult(
            selected_ids=(),
            required_ids=deduped,
            final_ids=deduped,
            candidate_count=len(candidates),
            fallback=True,
            reason="도구 셀렉터 미구성 — 지정 도구만 사용",
        )


def _to_source(raw: str) -> ToolSource:
    try:
        return ToolSource(raw)
    except ValueError:
        return ToolSource.INTERNAL
