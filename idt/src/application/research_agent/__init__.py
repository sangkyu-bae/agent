"""Research agent application module."""

from src.application.research_agent.workflow import (
    SelfCorrectiveRAGWorkflow,
    create_initial_state,
)

__all__ = [
    "SelfCorrectiveRAGWorkflow",
    "create_initial_state",
]
