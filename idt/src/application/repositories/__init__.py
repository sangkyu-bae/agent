"""Repository interfaces for the application layer.

These abstract interfaces define contracts for data access operations
without specifying implementation details.
"""
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)

__all__ = [
    "ConversationMessageRepository",
    "ConversationSummaryRepository",
]
