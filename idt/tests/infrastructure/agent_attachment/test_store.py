"""AgentAttachmentStore save/load/delete/purge 테스트 (Design §8.2)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.domain.agent_attachment.value_objects import AttachmentType
from src.infrastructure.agent_attachment.store import AgentAttachmentStore


def _store(tmp_path: Path) -> AgentAttachmentStore:
    return AgentAttachmentStore(str(tmp_path / "att"))


class TestSaveLoad:
    def test_save_returns_ref_and_writes_file(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        stored = store.save(
            file_bytes=b"hello-excel",
            filename="sales.xlsx",
            attachment_type=AttachmentType.EXCEL,
            owner_user_id="42",
        )
        assert len(stored.file_id) == 32
        assert stored.type == AttachmentType.EXCEL
        assert stored.owner_user_id == "42"
        assert stored.size == len(b"hello-excel")
        assert Path(stored.file_path).read_bytes() == b"hello-excel"
        assert stored.file_path.endswith(".xlsx")

    def test_load_roundtrip(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        saved = store.save(
            file_bytes=b"data", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="7",
        )
        loaded = store.load(saved.file_id)
        assert loaded is not None
        assert loaded.file_id == saved.file_id
        assert loaded.owner_user_id == "7"
        assert loaded.file_path == saved.file_path

    def test_load_unknown_returns_none(self, tmp_path: Path) -> None:
        assert _store(tmp_path).load("0" * 32) is None

    def test_load_invalid_id_blocks_traversal(self, tmp_path: Path) -> None:
        # 경로 조작 시도 → 형식 검증으로 차단(None)
        assert _store(tmp_path).load("../../etc/passwd") is None

    def test_filename_path_components_stripped(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        stored = store.save(
            file_bytes=b"x", filename="../../evil.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        assert stored.filename == "evil.xlsx"


class TestDelete:
    def test_delete_removes_file_and_meta(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        saved = store.save(
            file_bytes=b"x", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        store.delete(saved.file_id)
        assert store.load(saved.file_id) is None
        assert not Path(saved.file_path).exists()

    def test_delete_unknown_is_noop(self, tmp_path: Path) -> None:
        _store(tmp_path).delete("f" * 32)  # 예외 없이 통과

    def test_delete_invalid_id_is_noop(self, tmp_path: Path) -> None:
        _store(tmp_path).delete("../x")  # 예외 없이 통과


class TestPurgeExpired:
    def _age(self, store: AgentAttachmentStore, file_id: str, seconds: int) -> None:
        """메타의 created_at를 과거로 조작."""
        meta_path = store._meta_path(file_id)  # noqa: SLF001 (테스트 헬퍼)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        old = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        meta["created_at"] = old.isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    def test_purges_expired_keeps_fresh(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        old = store.save(
            file_bytes=b"x", filename="old.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        fresh = store.save(
            file_bytes=b"y", filename="new.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        self._age(store, old.file_id, seconds=7200)  # 2시간 전

        removed = store.purge_expired(ttl_seconds=3600)  # 1시간 TTL

        assert removed == 1
        assert store.load(old.file_id) is None
        assert store.load(fresh.file_id) is not None

    def test_save_triggers_lazy_purge(self, tmp_path: Path) -> None:
        store = AgentAttachmentStore(str(tmp_path / "att"), ttl_seconds=3600)
        old = store.save(
            file_bytes=b"x", filename="old.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        self._age(store, old.file_id, seconds=7200)

        # 다음 save가 만료분을 정리해야 함
        store.save(
            file_bytes=b"z", filename="trigger.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        assert store.load(old.file_id) is None
