"""문서 칩에 원문 뷰어 진입 정보를 덧붙인다 (Design §2.2, §3.3).

Design Ref: source-passage-viewer §6 — 예외 흡수의 안쪽 겹. 원본 존재 확인 실패는
그 문서의 original 만 None 으로 낮추고, 그 밖의 예외는 입력 목록을 그대로 돌려준다.
RunSourcesService 는 이 모듈을 import 하지 않고 enrich() 만 duck typing 으로 부른다.
"""
import dataclasses
from typing import Optional

from src.domain.agent_run.source_policy import RunEvidence, RunSourceItem, SourceKind
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.source_viewer.models import OriginalKind, ViewerRef
from src.domain.source_viewer.policy import PassagePolicy
from src.domain.source_viewer.ports import OriginalStorePort


class SourceViewerEnricher:
    def __init__(
        self, store: Optional[OriginalStorePort], logger: LoggerInterface,
    ) -> None:
        # store=None 이면 원본 보관 off — 모든 문서가 텍스트 뷰어로 열린다.
        self._store = store
        self._logger = logger

    async def enrich(
        self, items: list[RunSourceItem], evidence: RunEvidence, request_id: str,
    ) -> list[RunSourceItem]:
        try:
            return [await self._enrich_one(i, evidence, request_id) for i in items]
        except Exception as e:
            self._logger.warning(
                "source viewer enrich failed (sources unaffected)",
                exception=e, request_id=request_id,
            )
            return items

    async def _enrich_one(
        self, item: RunSourceItem, evidence: RunEvidence, request_id: str,
    ) -> RunSourceItem:
        if item.kind != SourceKind.DOCUMENT:
            return item
        document_id = item.key
        kb_id = PassagePolicy.kb_id_of(document_id, evidence.retrievals)
        passages = PassagePolicy.collect(document_id, evidence.retrievals)
        # Plan Out of Scope: KB 밖 일반 업로드 문서는 뷰어를 열지 않는다.
        if not kb_id or not passages:
            return item
        filename = PassagePolicy.filename_of(
            document_id, evidence.retrievals, evidence.filenames,
        )
        ref = ViewerRef(
            document_id=document_id,
            kb_id=kb_id,
            original=await self._original(document_id, filename, request_id),
            passages=passages,
        )
        return dataclasses.replace(item, viewer=ref.to_payload())

    async def _original(
        self, document_id: str, filename: str, request_id: str,
    ) -> Optional[OriginalKind]:
        kind = PassagePolicy.original_kind(filename)
        if self._store is None or kind is None:
            return None
        try:
            return kind if await self._store.exists(document_id) else None
        except Exception as e:
            # 잘못된 document_id(ValueError)·디스크 오류 — 텍스트 뷰어로 내려간다.
            self._logger.warning(
                "source viewer original lookup failed",
                exception=e, request_id=request_id, document_id=document_id,
            )
            return None
