"""ComposeAgentRequest 스키마 테스트 — fix-agent-composer B1/B2.

current_config/history 확장의 하위호환과 검증 규칙을 보증한다.
"""
import pytest
from pydantic import ValidationError

from src.application.agent_composer.schemas import (
    ComposeAgentRequest,
    ComposeCurrentConfig,
    ComposeHistoryTurn,
)


class TestComposeAgentRequestBackwardCompat:
    """B1: 신규 필드 없이 기존 요청 그대로 검증 통과."""

    def test_minimal_request_still_valid(self):
        req = ComposeAgentRequest(user_request="검색 에이전트 만들어줘")
        assert req.current_config is None
        assert req.history is None

    def test_legacy_full_request_still_valid(self):
        req = ComposeAgentRequest(
            user_request="검색 에이전트", name="검색이", llm_model_id="model-1"
        )
        assert req.name == "검색이"


class TestComposeAgentRequestExtension:
    """B2: current_config/history 검증 규칙."""

    def test_accepts_current_config_and_history(self):
        req = ComposeAgentRequest(
            user_request="tavily 도구 추가해줘",
            current_config=ComposeCurrentConfig(
                name="재무 리포터",
                system_prompt="당신은 재무 에이전트입니다.",
                tool_ids=["excel_export"],
                llm_model_id="model-1",
                temperature=0.7,
            ),
            history=[
                ComposeHistoryTurn(role="user", content="재무 에이전트 만들어줘"),
                ComposeHistoryTurn(role="assistant", content="초안: 재무 리포터"),
            ],
        )
        assert req.current_config.tool_ids == ["excel_export"]
        assert req.history[1].role == "assistant"

    def test_empty_current_config_allowed(self):
        """빈 폼(생성 초기 상태) 스냅샷도 허용."""
        req = ComposeAgentRequest(
            user_request="에이전트 만들어줘",
            current_config=ComposeCurrentConfig(),
        )
        assert req.current_config.tool_ids == []
        assert req.current_config.name is None

    def test_history_over_20_turns_rejected(self):
        turns = [
            ComposeHistoryTurn(role="user", content=f"메시지{i}") for i in range(21)
        ]
        with pytest.raises(ValidationError):
            ComposeAgentRequest(user_request="요청", history=turns)

    def test_history_turn_over_2000_chars_rejected(self):
        with pytest.raises(ValidationError):
            ComposeHistoryTurn(role="user", content="가" * 2001)

    def test_invalid_history_role_rejected(self):
        with pytest.raises(ValidationError):
            ComposeHistoryTurn(role="system", content="시스템 메시지")

    def test_temperature_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            ComposeCurrentConfig(temperature=2.5)

    def test_tool_ids_over_10_rejected(self):
        with pytest.raises(ValidationError):
            ComposeCurrentConfig(tool_ids=[f"t{i}" for i in range(11)])
