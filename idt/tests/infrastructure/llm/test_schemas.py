"""Tests for Claude LLM request/response schemas."""
import pytest

from src.infrastructure.llm.schemas import ClaudeModel, ClaudeRequest, ClaudeResponse


class TestClaudeModel:
    def test_opus_value(self):
        assert ClaudeModel.OPUS_4_5 == "claude-opus-4-5-20251101"

    def test_sonnet_value(self):
        assert ClaudeModel.SONNET_4_5 == "claude-sonnet-4-5-20250929"

    def test_haiku_value(self):
        assert ClaudeModel.HAIKU_4_5 == "claude-haiku-4-5-20251001"

    def test_is_string(self):
        assert isinstance(ClaudeModel.SONNET_4_5, str)


class TestClaudeRequest:
    def test_create_with_required_fields(self):
        request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert request.model == ClaudeModel.SONNET_4_5
        assert request.messages == [{"role": "user", "content": "Hello"}]

    def test_default_values(self):
        request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert request.system is None
        assert request.max_tokens == 4096
        assert request.temperature == 0.7
        assert request.stream is False

    def test_generates_unique_request_id(self):
        r1 = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "a"}],
        )
        r2 = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "b"}],
        )
        assert r1.request_id != r2.request_id

    def test_custom_request_id(self):
        request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "Hello"}],
            request_id="custom-id",
        )
        assert request.request_id == "custom-id"

    def test_empty_messages_raises_error(self):
        with pytest.raises(ValueError, match="messages must not be empty"):
            ClaudeRequest(model=ClaudeModel.SONNET_4_5, messages=[])

    def test_message_missing_role_raises_error(self):
        with pytest.raises(ValueError, match="must have 'role' and 'content'"):
            ClaudeRequest(
                model=ClaudeModel.SONNET_4_5,
                messages=[{"content": "Hello"}],
            )

    def test_message_missing_content_raises_error(self):
        with pytest.raises(ValueError, match="must have 'role' and 'content'"):
            ClaudeRequest(
                model=ClaudeModel.SONNET_4_5,
                messages=[{"role": "user"}],
            )

    def test_invalid_max_tokens_raises_error(self):
        with pytest.raises(ValueError, match="max_tokens must be greater than 0"):
            ClaudeRequest(
                model=ClaudeModel.SONNET_4_5,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=0,
            )

    def test_temperature_too_low_raises_error(self):
        with pytest.raises(ValueError, match="temperature must be between"):
            ClaudeRequest(
                model=ClaudeModel.SONNET_4_5,
                messages=[{"role": "user", "content": "Hello"}],
                temperature=-0.1,
            )

    def test_temperature_too_high_raises_error(self):
        with pytest.raises(ValueError, match="temperature must be between"):
            ClaudeRequest(
                model=ClaudeModel.SONNET_4_5,
                messages=[{"role": "user", "content": "Hello"}],
                temperature=1.1,
            )

    def test_with_system_prompt(self):
        request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": "Hello"}],
            system="You are a helpful assistant.",
        )
        assert request.system == "You are a helpful assistant."


class TestClaudeResponse:
    def test_create_response(self):
        response = ClaudeResponse(
            content="Hi there!",
            model="claude-sonnet-4-5-20250929",
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=5,
            request_id="req-123",
            latency_ms=150,
        )
        assert response.content == "Hi there!"
        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.stop_reason == "end_turn"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.request_id == "req-123"
        assert response.latency_ms == 150
