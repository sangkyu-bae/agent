"""Tests for parser domain value objects.

TDD: These tests are written first before implementation.
Domain tests use NO mocks as per CLAUDE.md rules.
"""
import pytest
from datetime import datetime

from src.domain.parser.value_objects import (
    ParserConfig,
    DocumentMetadata,
    generate_document_id,
    generate_chunk_id,
)


class TestParserConfig:
    """Tests for ParserConfig value object."""

    def test_create_default_config(self) -> None:
        """Default config should have expected values."""
        config = ParserConfig()
        assert config.chunk_size == 1000
        assert config.chunk_overlap == 200
        assert config.extract_images is False
        assert config.extract_tables is True
        assert config.ocr_enabled is False
        assert config.language == "ko"

    def test_create_custom_config(self) -> None:
        """Should accept custom configuration values."""
        config = ParserConfig(
            chunk_size=500,
            chunk_overlap=100,
            extract_images=True,
            extract_tables=False,
            ocr_enabled=True,
            language="en",
        )
        assert config.chunk_size == 500
        assert config.chunk_overlap == 100
        assert config.extract_images is True
        assert config.extract_tables is False
        assert config.ocr_enabled is True
        assert config.language == "en"

    def test_chunk_size_must_be_positive(self) -> None:
        """chunk_size must be greater than 0."""
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            ParserConfig(chunk_size=0)

    def test_chunk_size_negative_raises_error(self) -> None:
        """Negative chunk_size should raise error."""
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            ParserConfig(chunk_size=-100)

    def test_chunk_overlap_must_be_non_negative(self) -> None:
        """chunk_overlap must be >= 0."""
        with pytest.raises(ValueError, match="chunk_overlap must be >= 0"):
            ParserConfig(chunk_overlap=-1)

    def test_chunk_overlap_zero_is_valid(self) -> None:
        """chunk_overlap of 0 should be valid."""
        config = ParserConfig(chunk_overlap=0)
        assert config.chunk_overlap == 0

    def test_chunk_size_must_be_greater_than_overlap(self) -> None:
        """chunk_size must be greater than chunk_overlap."""
        with pytest.raises(ValueError, match="chunk_size must be > chunk_overlap"):
            ParserConfig(chunk_size=100, chunk_overlap=100)

    def test_chunk_size_less_than_overlap_raises_error(self) -> None:
        """chunk_size less than overlap should raise error."""
        with pytest.raises(ValueError, match="chunk_size must be > chunk_overlap"):
            ParserConfig(chunk_size=100, chunk_overlap=200)

    def test_language_valid_iso_639_1_codes(self) -> None:
        """Should accept valid ISO 639-1 language codes."""
        valid_codes = ["ko", "en", "ja", "zh", "de", "fr", "es"]
        for code in valid_codes:
            config = ParserConfig(language=code)
            assert config.language == code

    def test_language_invalid_code_raises_error(self) -> None:
        """Invalid language code should raise error."""
        with pytest.raises(ValueError, match="Invalid language code"):
            ParserConfig(language="invalid")

    def test_language_empty_string_raises_error(self) -> None:
        """Empty language code should raise error."""
        with pytest.raises(ValueError, match="Invalid language code"):
            ParserConfig(language="")

    def test_config_is_immutable(self) -> None:
        """ParserConfig should be immutable."""
        config = ParserConfig()
        with pytest.raises(AttributeError):
            config.chunk_size = 500

    def test_config_equality(self) -> None:
        """Two configs with same values should be equal."""
        config1 = ParserConfig(chunk_size=500, chunk_overlap=100)
        config2 = ParserConfig(chunk_size=500, chunk_overlap=100)
        assert config1 == config2

    def test_config_inequality(self) -> None:
        """Two configs with different values should not be equal."""
        config1 = ParserConfig(chunk_size=500)
        config2 = ParserConfig(chunk_size=600)
        assert config1 != config2


class TestGenerateDocumentId:
    """Tests for generate_document_id function."""

    def test_generates_expected_format(self) -> None:
        """Document ID should be {uuid8chars}_{filename}."""
        doc_id = generate_document_id("회사소개서.pdf")
        parts = doc_id.split("_", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 8  # uuid 8 chars
        assert parts[1] == "회사소개서"  # .pdf removed

    def test_removes_pdf_extension(self) -> None:
        """Should remove .pdf extension from filename."""
        doc_id = generate_document_id("report.pdf")
        assert not doc_id.endswith(".pdf")
        assert "report" in doc_id

    def test_replaces_spaces_with_underscore(self) -> None:
        """Spaces should be replaced with underscores."""
        doc_id = generate_document_id("my report.pdf")
        assert " " not in doc_id
        assert "my_report" in doc_id

    def test_unique_ids_for_same_filename(self) -> None:
        """Same filename should generate different IDs."""
        doc_id1 = generate_document_id("test.pdf")
        doc_id2 = generate_document_id("test.pdf")
        assert doc_id1 != doc_id2

    def test_handles_filename_without_extension(self) -> None:
        """Should work with filename without .pdf extension."""
        doc_id = generate_document_id("document")
        assert "document" in doc_id


class TestGenerateChunkId:
    """Tests for generate_chunk_id function."""

    def test_generates_expected_format(self) -> None:
        """Chunk ID should be {document_id}_p{page4digits}."""
        document_id = "a1b2c3d4_회사소개서"
        chunk_id = generate_chunk_id(document_id, 1)
        assert chunk_id == "a1b2c3d4_회사소개서_p0001"

    def test_pads_page_number_to_4_digits(self) -> None:
        """Page number should be zero-padded to 4 digits."""
        document_id = "a1b2c3d4_test"
        assert generate_chunk_id(document_id, 1) == "a1b2c3d4_test_p0001"
        assert generate_chunk_id(document_id, 99) == "a1b2c3d4_test_p0099"
        assert generate_chunk_id(document_id, 999) == "a1b2c3d4_test_p0999"
        assert generate_chunk_id(document_id, 9999) == "a1b2c3d4_test_p9999"

    def test_handles_large_page_numbers(self) -> None:
        """Should handle page numbers exceeding 4 digits."""
        document_id = "a1b2c3d4_test"
        chunk_id = generate_chunk_id(document_id, 12345)
        assert chunk_id == "a1b2c3d4_test_p12345"


class TestDocumentMetadata:
    """Tests for DocumentMetadata value object."""

    def test_create_with_required_fields(self) -> None:
        """Should create metadata with required fields."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        assert metadata.filename == "test.pdf"
        assert metadata.user_id == "user123"
        assert metadata.page == 1
        assert metadata.total_pages == 10
        assert metadata.parser == "pymupdf"

    def test_chunk_index_default_zero(self) -> None:
        """chunk_index should default to 0."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        assert metadata.chunk_index == 0

    def test_document_id_auto_generated(self) -> None:
        """document_id should be auto-generated."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        assert metadata.document_id is not None
        assert "test" in metadata.document_id
        assert len(metadata.document_id.split("_")[0]) == 8

    def test_chunk_id_auto_generated(self) -> None:
        """chunk_id should be auto-generated."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        assert metadata.chunk_id is not None
        assert "_p0001" in metadata.chunk_id

    def test_created_at_auto_set(self) -> None:
        """created_at should be auto-set to current time."""
        before = datetime.now()
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        after = datetime.now()
        assert before <= metadata.created_at <= after

    def test_created_by_equals_user_id(self) -> None:
        """created_by should equal user_id."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        assert metadata.created_by == "user123"

    def test_page_must_be_positive(self) -> None:
        """page must be >= 1."""
        with pytest.raises(ValueError, match="page must be >= 1"):
            DocumentMetadata(
                filename="test.pdf",
                user_id="user123",
                page=0,
                total_pages=10,
                parser="pymupdf",
            )

    def test_total_pages_must_be_positive(self) -> None:
        """total_pages must be >= 1."""
        with pytest.raises(ValueError, match="total_pages must be >= 1"):
            DocumentMetadata(
                filename="test.pdf",
                user_id="user123",
                page=1,
                total_pages=0,
                parser="pymupdf",
            )

    def test_page_cannot_exceed_total_pages(self) -> None:
        """page cannot exceed total_pages."""
        with pytest.raises(ValueError, match="page cannot exceed total_pages"):
            DocumentMetadata(
                filename="test.pdf",
                user_id="user123",
                page=11,
                total_pages=10,
                parser="pymupdf",
            )

    def test_filename_cannot_be_empty(self) -> None:
        """filename cannot be empty."""
        with pytest.raises(ValueError, match="filename cannot be empty"):
            DocumentMetadata(
                filename="",
                user_id="user123",
                page=1,
                total_pages=10,
                parser="pymupdf",
            )

    def test_user_id_cannot_be_empty(self) -> None:
        """user_id cannot be empty."""
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            DocumentMetadata(
                filename="test.pdf",
                user_id="",
                page=1,
                total_pages=10,
                parser="pymupdf",
            )

    def test_parser_cannot_be_empty(self) -> None:
        """parser cannot be empty."""
        with pytest.raises(ValueError, match="parser cannot be empty"):
            DocumentMetadata(
                filename="test.pdf",
                user_id="user123",
                page=1,
                total_pages=10,
                parser="",
            )

    def test_metadata_is_immutable(self) -> None:
        """DocumentMetadata should be immutable."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
        )
        with pytest.raises(AttributeError):
            metadata.page = 2

    def test_to_dict_returns_all_fields(self) -> None:
        """to_dict should return all metadata fields as dict."""
        metadata = DocumentMetadata(
            filename="test.pdf",
            user_id="user123",
            page=1,
            total_pages=10,
            parser="pymupdf",
            chunk_index=0,
        )
        result = metadata.to_dict()
        assert result["filename"] == "test.pdf"
        assert result["user_id"] == "user123"
        assert result["page"] == 1
        assert result["total_pages"] == 10
        assert result["parser"] == "pymupdf"
        assert result["chunk_index"] == 0
        assert "document_id" in result
        assert "chunk_id" in result
        assert "created_at" in result
        assert "created_by" in result
