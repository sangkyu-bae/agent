"""Tests for DocumentCategory enum."""
import pytest

from src.domain.pipeline.enums.document_category import DocumentCategory


class TestDocumentCategoryValues:
    """Test DocumentCategory enum values."""

    def test_loan_finance_category_exists(self):
        """Test LOAN_FINANCE category value."""
        assert DocumentCategory.LOAN_FINANCE.value == "loan_finance"

    def test_it_system_category_exists(self):
        """Test IT_SYSTEM category value."""
        assert DocumentCategory.IT_SYSTEM.value == "it_system"

    def test_security_access_category_exists(self):
        """Test SECURITY_ACCESS category value."""
        assert DocumentCategory.SECURITY_ACCESS.value == "security_access"

    def test_hr_category_exists(self):
        """Test HR category value."""
        assert DocumentCategory.HR.value == "hr"

    def test_accounting_legal_category_exists(self):
        """Test ACCOUNTING_LEGAL category value."""
        assert DocumentCategory.ACCOUNTING_LEGAL.value == "accounting_legal"

    def test_general_category_exists(self):
        """Test GENERAL category value."""
        assert DocumentCategory.GENERAL.value == "general"

    def test_all_categories_count(self):
        """Test total number of categories."""
        assert len(DocumentCategory) == 6


class TestDocumentCategoryDescription:
    """Test DocumentCategory description property."""

    def test_loan_finance_description_returns_korean(self):
        """Test LOAN_FINANCE description is Korean text."""
        desc = DocumentCategory.LOAN_FINANCE.description
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_it_system_description_returns_korean(self):
        """Test IT_SYSTEM description is Korean text."""
        desc = DocumentCategory.IT_SYSTEM.description
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_hr_description_returns_korean(self):
        """Test HR description is Korean text."""
        desc = DocumentCategory.HR.description
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_all_categories_have_description(self):
        """Test all categories have non-empty description."""
        for category in DocumentCategory:
            desc = category.description
            assert isinstance(desc, str), f"{category} description is not string"
            assert len(desc) > 0, f"{category} description is empty"


class TestDocumentCategoryStringConversion:
    """Test DocumentCategory string conversion."""

    def test_value_returns_string(self):
        """Test .value returns string value."""
        assert DocumentCategory.LOAN_FINANCE.value == "loan_finance"
        assert DocumentCategory.IT_SYSTEM.value == "it_system"

    def test_category_inherits_from_str(self):
        """Test category can be used as string."""
        category = DocumentCategory.GENERAL
        # Can be used in string operations
        assert "general" in category
        assert category.upper() == "GENERAL"

    def test_category_from_string_value(self):
        """Test creating category from string value."""
        category = DocumentCategory("loan_finance")
        assert category == DocumentCategory.LOAN_FINANCE

    def test_invalid_string_raises_error(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            DocumentCategory("invalid_category")
