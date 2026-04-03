"""Classification prompt builder for document categorization."""
from typing import List

from langchain_core.documents import Document

from src.domain.pipeline.enums.document_category import DocumentCategory


CLASSIFICATION_SYSTEM_PROMPT = """You are a document classification expert for a Korean financial organization.
Your task is to classify documents into one of the following categories based on their content.

Categories:
- loan_finance: Documents related to loans, credit, interest rates, financial products, and banking services.
- it_system: Technical documentation, system specifications, IT policies, software guides, and technology-related documents.
- security_access: Security policies, access control procedures, authentication guidelines, and information security documents.
- hr: Human resources documents, employment policies, personnel management, and labor-related documents.
- accounting_legal: Accounting procedures, legal documents, compliance guidelines, financial reporting, and audit-related documents.
- general: Documents that don't fit clearly into any other category.

Analyze the provided document excerpts carefully and determine the most appropriate category.
Consider the overall theme, terminology used, and the purpose of the document.

Respond ONLY with a valid JSON object containing:
- category: one of the category values listed above
- confidence: a float between 0.0 and 1.0 indicating your confidence
- reasoning: a brief explanation in Korean for your classification decision

Example response:
{"category": "loan_finance", "confidence": 0.92, "reasoning": "문서에 대출, 금리, 상환 조건 등 여신 관련 용어가 포함되어 있습니다."}
"""


def extract_sample_pages(documents: List[Document]) -> List[str]:
    """Extract sample pages from documents for classification.

    Extracts first, middle, and last pages to provide representative content.

    Args:
        documents: List of parsed document pages.

    Returns:
        List of sample page contents (1-3 pages).
    """
    if not documents:
        return []

    n = len(documents)

    if n == 1:
        return [documents[0].page_content]

    if n == 2:
        return [documents[0].page_content, documents[1].page_content]

    # 3+ pages: first, middle, last
    middle_idx = n // 2
    return [
        documents[0].page_content,
        documents[middle_idx].page_content,
        documents[n - 1].page_content,
    ]


def build_classification_prompt(sample_pages: List[str]) -> str:
    """Build classification prompt with sample pages.

    Args:
        sample_pages: List of sample page contents.

    Returns:
        Formatted prompt for classification.
    """
    categories_list = "\n".join([
        f"- {cat.value}: {cat.description}"
        for cat in DocumentCategory
    ])

    pages_text = "\n\n---\n\n".join([
        f"[Page {i+1}]\n{page[:2000]}"  # Truncate long pages
        for i, page in enumerate(sample_pages)
    ])

    return f"""Please classify the following document based on the sample pages provided.

Available categories:
{categories_list}

Document excerpts:
{pages_text}

Analyze the content and respond with a JSON object containing category, confidence, and reasoning.
"""
