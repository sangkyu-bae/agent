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


# ── chat-image-attachment Design §8.2 #8 ─────────────────────────────────────

_PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _normalizer(out: bytes = b"normalized", w: int = 12, h: int = 34) -> MagicMock:
    from src.domain.agent_attachment.value_objects import ImageDimensions

    n = MagicMock()
    n.normalize.return_value = (out, ImageDimensions(width=w, height=h, mime="image/png"))
    return n


class TestUploadImage:
    def test_image_calls_normalizer_and_stores_result(self, tmp_path: Path) -> None:
        norm = _normalizer()
        uc = UploadAttachmentUseCase(
            _store(tmp_path), MAX, MagicMock(),
            image_normalizer=norm, image_max_edge_px=1568, image_jpeg_quality=90,
        )
        stored = uc.execute(file_bytes=_PNG_HEAD, filename="shot.png", owner_user_id="9")
        norm.normalize.assert_called_once_with(_PNG_HEAD, max_edge_px=1568, jpeg_quality=90)
        assert stored.type == AttachmentType.IMAGE
        assert (stored.width, stored.height) == (12, 34)
        assert Path(stored.file_path).read_bytes() == b"normalized"
        assert stored.size == len(b"normalized")

    def test_excel_does_not_call_normalizer(self, tmp_path: Path) -> None:
        norm = _normalizer()
        uc = UploadAttachmentUseCase(
            _store(tmp_path), MAX, MagicMock(), image_normalizer=norm,
        )
        stored = uc.execute(file_bytes=b"abc", filename="a.xlsx", owner_user_id="9")
        norm.normalize.assert_not_called()
        assert stored.width is None

    def test_magic_mismatch_raises_before_normalizer(self, tmp_path: Path) -> None:
        norm = _normalizer()
        uc = UploadAttachmentUseCase(
            _store(tmp_path), MAX, MagicMock(), image_normalizer=norm,
        )
        with pytest.raises(InvalidAttachmentError):
            uc.execute(file_bytes=b"GIF89a" + b"\x00" * 10, filename="a.png", owner_user_id="9")
        norm.normalize.assert_not_called()

    def test_oversize_checked_on_original_bytes(self, tmp_path: Path) -> None:
        from src.domain.agent_attachment.exceptions import AttachmentTooLargeError

        uc = UploadAttachmentUseCase(
            _store(tmp_path), 16, MagicMock(), image_normalizer=_normalizer(),
        )
        with pytest.raises(AttachmentTooLargeError):
            uc.execute(file_bytes=_PNG_HEAD + b"\x00" * 100, filename="a.png", owner_user_id="9")

    def test_dimensions_survive_store_roundtrip(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        uc = UploadAttachmentUseCase(store, MAX, MagicMock(), image_normalizer=_normalizer())
        stored = uc.execute(file_bytes=_PNG_HEAD, filename="shot.png", owner_user_id="9")
        loaded = store.load(stored.file_id)
        assert loaded is not None
        assert (loaded.width, loaded.height) == (12, 34)


class TestResolverImage:
    def test_image_dict_includes_mime_and_file_name(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        saved = store.save(
            file_bytes=b"x", filename="chart.webp",
            attachment_type=AttachmentType.IMAGE, owner_user_id="5",
            width=3, height=4,
        )
        out = AttachmentResolver(store, MagicMock()).resolve(saved.file_id, viewer_user_id="5")
        assert out == {
            "type": "image",
            "file_path": saved.file_path,
            "user_id": "5",
            "mime": "image/webp",
            "file_name": "chart.webp",
            "width": 3,
            "height": 4,
        }

    def test_excel_dict_unchanged(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        saved = store.save(
            file_bytes=b"x", filename="a.xlsx",
            attachment_type=AttachmentType.EXCEL, owner_user_id="5",
        )
        out = AttachmentResolver(store, MagicMock()).resolve(saved.file_id, viewer_user_id="5")
        assert out == {"type": "excel", "file_path": saved.file_path, "user_id": "5"}
