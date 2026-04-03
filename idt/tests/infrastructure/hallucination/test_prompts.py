"""Tests for hallucination evaluation prompts."""

import pytest

from src.infrastructure.hallucination.prompts import (
    HALLUCINATION_EVALUATION_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_HUMAN_TEMPLATE,
)


class TestHallucinationPrompts:
    """Tests for hallucination evaluation prompt templates."""

    def test_system_prompt_exists(self) -> None:
        """System prompt should be defined and non-empty."""
        assert HALLUCINATION_EVALUATION_SYSTEM_PROMPT
        assert isinstance(HALLUCINATION_EVALUATION_SYSTEM_PROMPT, str)
        assert len(HALLUCINATION_EVALUATION_SYSTEM_PROMPT.strip()) > 0

    def test_human_template_exists(self) -> None:
        """Human template should be defined and non-empty."""
        assert HALLUCINATION_EVALUATION_HUMAN_TEMPLATE
        assert isinstance(HALLUCINATION_EVALUATION_HUMAN_TEMPLATE, str)
        assert len(HALLUCINATION_EVALUATION_HUMAN_TEMPLATE.strip()) > 0

    def test_human_template_has_documents_placeholder(self) -> None:
        """Human template should contain {documents} placeholder."""
        assert "{documents}" in HALLUCINATION_EVALUATION_HUMAN_TEMPLATE

    def test_human_template_has_generation_placeholder(self) -> None:
        """Human template should contain {generation} placeholder."""
        assert "{generation}" in HALLUCINATION_EVALUATION_HUMAN_TEMPLATE
