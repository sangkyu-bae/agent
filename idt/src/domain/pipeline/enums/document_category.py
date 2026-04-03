"""Document category enumeration for pipeline classification."""
from enum import Enum


class DocumentCategory(str, Enum):
    """Categories for document classification.

    Each category represents a document type with specific chunking requirements.
    """

    LOAN_FINANCE = "loan_finance"
    IT_SYSTEM = "it_system"
    SECURITY_ACCESS = "security_access"
    HR = "hr"
    ACCOUNTING_LEGAL = "accounting_legal"
    GENERAL = "general"

    @property
    def description(self) -> str:
        """Return Korean description of the category."""
        descriptions = {
            DocumentCategory.LOAN_FINANCE: "여신/금융 관련 문서",
            DocumentCategory.IT_SYSTEM: "IT 시스템 관련 문서",
            DocumentCategory.SECURITY_ACCESS: "보안/접근권한 관련 문서",
            DocumentCategory.HR: "인사/노무 관련 문서",
            DocumentCategory.ACCOUNTING_LEGAL: "회계/법무 관련 문서",
            DocumentCategory.GENERAL: "일반 문서",
        }
        return descriptions[self]
