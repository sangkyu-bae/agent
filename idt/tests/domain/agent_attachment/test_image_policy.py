"""이미지 첨부 정책 테스트 — chat-image-attachment Design §3.1 / §8.2 #1, #2."""
import pytest

from src.domain.agent_attachment.exceptions import (
    InvalidAttachmentError,
    TooManyImagesError,
    VisionNotSupportedError,
)
from src.domain.agent_attachment.policies import (
    AttachmentPolicy,
    ImageAttachmentPolicy,
)
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    ImageDimensions,
    StoredAttachment,
)

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 12
WEBP_HEAD = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 4
GIF_HEAD = b"GIF89a" + b"\x00" * 10


class TestResolveImageType:
    @pytest.mark.parametrize("name", ["a.png", "B.JPG", "c.jpeg", "d.webp", "x.y.png"])
    def test_image_extensions_resolve_to_image(self, name: str) -> None:
        assert AttachmentPolicy.resolve_type(name) == AttachmentType.IMAGE

    @pytest.mark.parametrize("name", ["a.gif", "a.svg", "a.heic", "a.bmp", "a.pdf"])
    def test_non_allowed_image_extensions_raise(self, name: str) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.resolve_type(name)

    def test_excel_still_resolves(self) -> None:
        assert AttachmentPolicy.resolve_type("s.xlsx") == AttachmentType.EXCEL


class TestSniffImageMime:
    @pytest.mark.parametrize(
        ("head", "mime"),
        [
            (PNG_HEAD, "image/png"),
            (JPEG_HEAD, "image/jpeg"),
            (WEBP_HEAD, "image/webp"),
        ],
    )
    def test_known_magic(self, head: bytes, mime: str) -> None:
        assert AttachmentPolicy.sniff_image_mime(head) == mime

    @pytest.mark.parametrize("head", [GIF_HEAD, b"", b"RIFF\x00\x00\x00\x00WAVE", b"\x89PN"])
    def test_unknown_magic_returns_none(self, head: bytes) -> None:
        assert AttachmentPolicy.sniff_image_mime(head) is None


class TestValidateImageBytes:
    def test_matching_ext_and_magic_returns_mime(self) -> None:
        assert AttachmentPolicy.validate_image_bytes("a.png", PNG_HEAD) == "image/png"

    def test_jpg_and_jpeg_both_accept_jpeg_magic(self) -> None:
        assert AttachmentPolicy.validate_image_bytes("a.jpg", JPEG_HEAD) == "image/jpeg"
        assert AttachmentPolicy.validate_image_bytes("a.jpeg", JPEG_HEAD) == "image/jpeg"

    def test_mismatch_raises(self) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.validate_image_bytes("a.png", JPEG_HEAD)

    def test_unknown_magic_raises(self) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.validate_image_bytes("a.png", GIF_HEAD)


class TestImageAttachmentPolicy:
    def test_count_within_limit_passes(self) -> None:
        ImageAttachmentPolicy.validate_count(5, max_count=5)
        ImageAttachmentPolicy.validate_count(0, max_count=5)

    def test_count_over_limit_raises(self) -> None:
        with pytest.raises(TooManyImagesError):
            ImageAttachmentPolicy.validate_count(6, max_count=5)

    def test_marker_lists_names(self) -> None:
        assert ImageAttachmentPolicy.marker(["a.png", "b.jpg"]) == "[이미지 첨부: a.png, b.jpg]"

    def test_marker_empty_is_empty_string(self) -> None:
        assert ImageAttachmentPolicy.marker([]) == ""

    def test_unsupported_marker_mentions_model_limit(self) -> None:
        out = ImageAttachmentPolicy.unsupported_marker(["a.png"])
        assert out.startswith("[이미지 첨부: a.png")
        assert "이미지를 볼 수 없" in out

    def test_mime_for_extension(self) -> None:
        assert ImageAttachmentPolicy.mime_for("x.PNG") == "image/png"
        assert ImageAttachmentPolicy.mime_for("x.jpg") == "image/jpeg"
        assert ImageAttachmentPolicy.mime_for("x.webp") == "image/webp"


class TestValueObjects:
    def test_image_dimensions_frozen(self) -> None:
        d = ImageDimensions(width=10, height=20, mime="image/png")
        with pytest.raises(Exception):
            d.width = 3  # type: ignore[misc]

    def test_stored_attachment_width_height_default_none(self) -> None:
        s = StoredAttachment(
            file_id="f", type=AttachmentType.EXCEL, filename="a.xlsx",
            size=1, owner_user_id="u", file_path="/p",
        )
        assert s.width is None and s.height is None

    def test_vision_not_supported_error_carries_model_name(self) -> None:
        err = VisionNotSupportedError("gpt-x")
        assert "gpt-x" in str(err)
