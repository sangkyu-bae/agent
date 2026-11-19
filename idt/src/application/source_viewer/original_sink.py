"""업로드·삭제 경로에 꽂히는 원본 보관 협력자 (Design §2.2, §6).

Design Ref: source-passage-viewer §6 — 예외 흡수의 안쪽 겹. 어떤 실패도 호출자에게
올리지 않는다(호출 지점이 바깥 겹으로 한 번 더 감싼다). 원본 뷰어가 렌더할 수 있는
형식(pdf/docx)만 보관해 디스크를 아낀다.
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.source_viewer.policy import PassagePolicy
from src.domain.source_viewer.ports import OriginalStorePort


class OriginalSink:
    def __init__(self, store: OriginalStorePort, logger: LoggerInterface) -> None:
        self._store = store
        self._logger = logger

    async def save(
        self, document_id: str, filename: str, data: bytes, request_id: str,
    ) -> None:
        if PassagePolicy.original_kind(filename) is None:
            return
        try:
            await self._store.save(document_id, data)
        except Exception as e:
            self._logger.warning(
                "source viewer original save failed (upload unaffected)",
                exception=e, request_id=request_id, document_id=document_id,
            )

    async def delete(self, document_id: str, request_id: str) -> None:
        try:
            await self._store.delete(document_id)
        except Exception as e:
            self._logger.warning(
                "source viewer original delete failed (delete unaffected)",
                exception=e, request_id=request_id, document_id=document_id,
            )
