"""로컬 임시 디렉토리 기반 첨부 저장소 + 사이드카 메타 (Design §3.2).

- 저장 경로(결정적): {upload_dir}/{file_id}{ext}
- 메타(JSON):        {upload_dir}/{file_id}.meta.json
- DB 미사용 (과도한 추상화 회피). 단일 프로세스(WS sticky) 전제.

보안:
- file_id = uuid4 hex (추측·열거 불가)
- 경로는 file_id로만 구성하고 file_id 형식을 검증 → path traversal 차단
- 원본 filename은 표시용으로만 보관(경로 컴포넌트 제거)
"""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Optional

from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)

_FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _is_valid_file_id(file_id: str) -> bool:
    return bool(_FILE_ID_RE.match(file_id or ""))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentAttachmentStore:
    """첨부 파일을 임시 디렉토리에 저장/조회/삭제한다 (AttachmentStoreInterface 구현).

    Design §7: run 종료 시 즉시 삭제가 기본이며, 비정상 종료로 남은 orphan은
    TTL 백업 정리(purge_expired)로 회수한다. save() 시 기회적으로 lazy sweep 한다.
    """

    def __init__(self, upload_dir: str, ttl_seconds: int = 0) -> None:
        self._dir = Path(upload_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_seconds

    def save(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        attachment_type: AttachmentType,
        owner_user_id: str,
    ) -> StoredAttachment:
        if self._ttl_seconds > 0:
            self.purge_expired(self._ttl_seconds)  # lazy TTL 백업 정리
        file_id = uuid.uuid4().hex
        ext = PurePath(filename).suffix.lower()
        safe_name = PurePath(filename).name  # 경로 컴포넌트 제거

        data_path = self._data_path(file_id, ext)
        data_path.write_bytes(file_bytes)

        meta = {
            "file_id": file_id,
            "type": attachment_type.value,
            "filename": safe_name,
            "size": len(file_bytes),
            "owner_user_id": owner_user_id,
            "created_at": _utcnow_iso(),
            "ext": ext,
        }
        self._meta_path(file_id).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        return StoredAttachment(
            file_id=file_id,
            type=attachment_type,
            filename=safe_name,
            size=len(file_bytes),
            owner_user_id=owner_user_id,
            file_path=str(data_path),
        )

    def load(self, file_id: str) -> Optional[StoredAttachment]:
        if not _is_valid_file_id(file_id):
            return None
        meta_path = self._meta_path(file_id)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        data_path = self._data_path(file_id, meta.get("ext", ""))
        if not data_path.exists():
            return None
        return StoredAttachment(
            file_id=file_id,
            type=AttachmentType(meta["type"]),
            filename=meta["filename"],
            size=meta["size"],
            owner_user_id=str(meta["owner_user_id"]),
            file_path=str(data_path),
        )

    def delete(self, file_id: str) -> None:
        if not _is_valid_file_id(file_id):
            return
        meta_path = self._meta_path(file_id)
        ext = ""
        if meta_path.exists():
            try:
                ext = json.loads(meta_path.read_text(encoding="utf-8")).get("ext", "")
            except (ValueError, OSError):
                ext = ""
        self._data_path(file_id, ext).unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    def purge_expired(self, ttl_seconds: int) -> int:
        """created_at 기준 만료된 첨부(파일+메타)를 삭제하고 삭제 개수를 반환.

        Design §7 TTL 백업 정리 — 비정상 종료로 finally cleanup이 누락된 orphan 회수.
        파싱 불가/손상 메타는 보수적으로 건너뛴다(다음 sweep에서 재시도).
        """
        if ttl_seconds <= 0:
            return 0
        now = datetime.now(timezone.utc)
        removed = 0
        for meta_path in self._dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                created = datetime.fromisoformat(meta["created_at"])
            except (ValueError, OSError, KeyError):
                continue
            if (now - created).total_seconds() <= ttl_seconds:
                continue
            file_id = meta.get("file_id", meta_path.name[: -len(".meta.json")])
            self.delete(file_id)
            removed += 1
        return removed

    def _data_path(self, file_id: str, ext: str) -> Path:
        return self._dir / f"{file_id}{ext}"

    def _meta_path(self, file_id: str) -> Path:
        return self._dir / f"{file_id}.meta.json"
