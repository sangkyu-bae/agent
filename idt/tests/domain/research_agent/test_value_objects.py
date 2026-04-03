"""Tests for research_agent domain value objects."""

import pytest
from enum import Enum
from pydantic import BaseModel, ValidationError

from src.domain.research_agent.value_objects import (
    RouteType,
    RouteDecision,
    RelevanceResult,
)


class TestRouteType:
    """Tests for RouteType enum."""

    def test_is_enum(self) -> None:
        """RouteType should be an Enum."""
        assert issubclass(RouteType, Enum)

    def test_has_web_search_value(self) -> None:
        """RouteType should have WEB_SEARCH value."""
        assert RouteType.WEB_SEARCH.value == "web_search"

    def test_has_rag_value(self) -> None:
        """RouteType should have RAG value."""
        assert RouteType.RAG.value == "rag"

    def test_web_search_is_string_enum(self) -> None:
        """RouteType.WEB_SEARCH should be a string."""
        assert isinstance(RouteType.WEB_SEARCH.value, str)

    def test_rag_is_string_enum(self) -> None:
        """RouteType.RAG should be a string."""
        assert isinstance(RouteType.RAG.value, str)


class TestRouteDecision:
    """Tests for RouteDecision value object."""

    def test_is_pydantic_basemodel(self) -> None:
        """RouteDecision should be a Pydantic BaseModel."""
        assert issubclass(RouteDecision, BaseModel)

    def test_creates_with_web_search_route(self) -> None:
        """RouteDecision should accept WEB_SEARCH route."""
        decision = RouteDecision(route=RouteType.WEB_SEARCH, reason="Current events query")
        assert decision.route == RouteType.WEB_SEARCH
        assert decision.reason == "Current events query"

    def test_creates_with_rag_route(self) -> None:
        """RouteDecision should accept RAG route."""
        decision = RouteDecision(route=RouteType.RAG, reason="Document-based query")
        assert decision.route == RouteType.RAG
        assert decision.reason == "Document-based query"

    def test_route_field_required(self) -> None:
        """route field should be required."""
        with pytest.raises(ValidationError):
            RouteDecision(reason="Some reason")

    def test_reason_field_required(self) -> None:
        """reason field should be required."""
        with pytest.raises(ValidationError):
            RouteDecision(route=RouteType.RAG)

    def test_reason_must_be_string(self) -> None:
        """reason field must be a string."""
        with pytest.raises(ValidationError):
            RouteDecision(route=RouteType.RAG, reason=123)

    def test_route_must_be_route_type(self) -> None:
        """route field must be RouteType enum."""
        with pytest.raises(ValidationError):
            RouteDecision(route="invalid", reason="Some reason")


class TestRelevanceResult:
    """Tests for RelevanceResult value object."""

    def test_is_pydantic_basemodel(self) -> None:
        """RelevanceResult should be a Pydantic BaseModel."""
        assert issubclass(RelevanceResult, BaseModel)

    def test_is_relevant_field_true(self) -> None:
        """is_relevant field should accept True."""
        result = RelevanceResult(is_relevant=True)
        assert result.is_relevant is True

    def test_is_relevant_field_false(self) -> None:
        """is_relevant field should accept False."""
        result = RelevanceResult(is_relevant=False)
        assert result.is_relevant is False

    def test_is_relevant_field_required(self) -> None:
        """is_relevant field should be required."""
        with pytest.raises(ValidationError):
            RelevanceResult()

    def test_is_relevant_field_must_be_bool(self) -> None:
        """is_relevant field must be boolean."""
        with pytest.raises(ValidationError):
            RelevanceResult(is_relevant="not a bool")
