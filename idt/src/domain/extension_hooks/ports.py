"""코어 확장 포트 4종.

Design Ref: graph-rag-foundation §3.1 — 확장 모듈이 구현하고, 코어는 호출만 한다.
코어 호출 지점은 예외를 삼켜 답변·업로드·삭제 경로를 깨지 않는다(§6.2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.extension_hooks.events import (
    DocumentDeletedEvent,
    DocumentIngestedEvent,
    SupplementalQuery,
    SupplementalResult,
)


class PostIngestHook(ABC):
    @abstractmethod
    async def on_document_ingested(
        self, event: DocumentIngestedEvent, request_id: str
    ) -> None:
        raise NotImplementedError


class DocumentDeletionHook(ABC):
    @abstractmethod
    async def on_document_deleted(
        self, event: DocumentDeletedEvent, request_id: str
    ) -> None:
        raise NotImplementedError


class SupplementalRetrievalSource(ABC):
    """도구의 최종 검색 결과에 RRF 로 한 번 더 합칠 보조 결과 공급자.

    노출 단계·권한 판단은 구현체 책임이다. 실행하지 않을 때는 빈 hits 와
    skip_reason 을 돌려준다(예외 대신).
    """

    @abstractmethod
    async def retrieve(self, query: SupplementalQuery) -> SupplementalResult:
        raise NotImplementedError


class FeatureExposurePort(ABC):
    """기능을 화면·저장 API 에 드러낼지 판단한다."""

    @abstractmethod
    async def is_visible(self, feature: str, caller_is_admin: bool) -> bool:
        raise NotImplementedError
