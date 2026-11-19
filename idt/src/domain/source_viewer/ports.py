"""원본 파일 저장 포트 (Design §3.1).

로컬 디스크 구현이 기본이며, 오브젝트 스토리지로 바꿀 때 이 포트만 구현한다.
구현은 잘못된 document_id 에 ValueError 를 던진다(경로 조작 차단, policy.storage_key).
"""
from typing import Optional, Protocol


class OriginalStorePort(Protocol):
    async def save(self, document_id: str, data: bytes) -> None: ...

    async def exists(self, document_id: str) -> bool: ...

    async def open(self, document_id: str) -> Optional[bytes]: ...

    async def delete(self, document_id: str) -> None: ...
