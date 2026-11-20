"""원본 파일 로컬 디스크 저장소 (Design §3.4, §7).

경로: `{root}/{document_id[:2]}/{document_id}` (확장자 없음 — 형식은 파일명으로 판정).
document_id 는 storage_key 가 UUID 로 검증하고, 최종 경로가 root 안인지 한 번 더 본다.
파일 I/O 는 이벤트 루프를 막지 않게 스레드로 넘긴다.
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from src.domain.source_viewer.policy import storage_key


class LocalDiskOriginalStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, document_id: str) -> Path:
        key = storage_key(document_id)
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError("storage path escapes root")
        return path

    async def save(self, document_id: str, data: bytes) -> None:
        path = self._path(document_id)
        await asyncio.to_thread(_atomic_write, path, data)

    async def exists(self, document_id: str) -> bool:
        path = self._path(document_id)
        return await asyncio.to_thread(path.is_file)

    async def open(self, document_id: str) -> Optional[bytes]:
        path = self._path(document_id)
        return await asyncio.to_thread(_read_or_none, path)

    async def delete(self, document_id: str) -> None:
        path = self._path(document_id)
        await asyncio.to_thread(path.unlink, missing_ok=True)


def _atomic_write(path: Path, data: bytes) -> None:
    """임시 파일에 쓴 뒤 교체 — 쓰다 만 파일이 원본으로 보이지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_or_none(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
