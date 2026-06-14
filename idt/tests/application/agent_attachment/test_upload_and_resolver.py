"""UploadAttachmentUseCase + AttachmentResolver 테스트 (Design §8.2)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.agent_attachment.resolver import AttachmentResolver
from src.application.agent_attachment.upload_use_case import UploadAttachmentUseCase
from src.domain.agent_attachment.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentNotFoundError,
    InvalidAttachmentError,
)
from src.domain.agent_attachment.value_objects import AttachmentType
from src.infrastructure.agent_attachment.store import AgentAttachmentStore

MAX = 10 * 1024 * 1024


def _store(tmp_path: Path) -> AgentAttachmentStore:
    return AgentAttachmentStore(str(tmp_path / "att"))


class TestUploadUseCase:
    def test_valid_upload_saves_and_returns(self, tmp_path: Path) -> None:
        uc = UploadAttachmentUseCase(_store(tmp_path), MAX, MagicMock())
        stored = uc.execute(
            file_bytes=b"abc", filename="a.xlsx", owner_user_id="9",
        )
        assert stored.owner_user_id == "9"
        assert Path(stored.file_path).exists()

    def test_invalid_extension_raises(self, tmp_path: Path) -> None:
        uc = UploadAttachmentUseCase(_store(tmp_path), MAX, MagicMock())
        with pytest.raises(InvalidAttachmentError):
            uc.execute(file_bytes=b"abc", filename="a.csv", owner_user_id="9")


class TestResolver:
    def test_resolve_returns_attachment_dict(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        saved = store.save(
            file_bytes=b"x", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="5",
        )
        resolver = AttachmentResolver(store, MagicMock())
        out = resolver.resolve(saved.file_id, viewer_user_id="5")
        assert out == {
            "type": "excel",
            "file_path": saved.file_path,
            "user_id": "5",
        }

    def test_resolve_not_found_raises(self, tmp_path: Path) -> None:
        resolver = AttachmentResolver(_store(tmp_path), MagicMock())
        with pytest.raises(AttachmentNotFoundError):
            resolver.resolve("0" * 32, viewer_user_id="5")

    def test_resolve_other_owner_denied(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        from src.domain.agent_attachment.value_objects import AttachmentType
        saved = store.save(
            file_bytes=b"x", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="owner",
        )
        resolver = AttachmentResolver(store, MagicMock())
        with pytest.raises(AttachmentAccessDeniedError):
            resolver.resolve(saved.file_id, viewer_user_id="intruder")

    def test_cleanup_deletes_and_swallows_errors(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        from src.domain.agent_attachment.value_objects import AttachmentType
        saved = store.save(
            file_bytes=b"x", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="1",
        )
        resolver = AttachmentResolver(store, MagicMock())
        # 존재 + 비존재 file_id 혼합 — 예외 없이 정리
        resolver.cleanup([saved.file_id, "f" * 32])
        assert store.load(saved.file_id) is None
