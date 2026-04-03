"""AgentSpecInferenceService 테스트 (LLM Mock)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.auto_agent_builder.schemas import ConversationTurn
from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService


def _make_service() -> AgentSpecInferenceService:
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return AgentSpecInferenceService(model_name="gpt-4o", logger=logger)


def _mock_llm_response(data: dict):
    """ChatOpenAI.ainvoke Mock 반환값 생성."""
    msg = MagicMock()
    msg.content = json.dumps(data)
    return msg


class TestInfer:

    @pytest.mark.asyncio
    async def test_infer_returns_spec_result_when_confident(self):
        service = _make_service()
        response_data = {
            "confidence": 0.9,
            "tool_ids": ["internal_document_search", "excel_export"],
            "middlewares": [{"type": "summarization", "config": {}}],
            "system_prompt": "분석 전문가입니다.",
            "clarifying_questions": [],
            "reasoning": "문서 검색 후 엑셀 출력",
        }
        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=_mock_llm_response(response_data))
            MockLLM.return_value = mock_instance

            result = await service.infer(
                user_request="분기 보고서 엑셀로 만들어줘",
                conversation_history=[],
                request_id="req-1",
            )

        assert result.confidence == 0.9
        assert result.tool_ids == ["internal_document_search", "excel_export"]
        assert len(result.middleware_configs) == 1
        assert result.clarifying_questions == []
        assert result.reasoning == "문서 검색 후 엑셀 출력"

    @pytest.mark.asyncio
    async def test_infer_returns_questions_when_uncertain(self):
        service = _make_service()
        response_data = {
            "confidence": 0.5,
            "tool_ids": ["internal_document_search"],
            "middlewares": [],
            "system_prompt": "",
            "clarifying_questions": ["PII 데이터 있나요?", "웹 검색도 필요한가요?"],
            "reasoning": "불확실",
        }
        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=_mock_llm_response(response_data))
            MockLLM.return_value = mock_instance

            result = await service.infer("에이전트 만들어", [], "req-2")

        assert result.confidence == 0.5
        assert len(result.clarifying_questions) == 2

    @pytest.mark.asyncio
    async def test_infer_includes_history_in_messages(self):
        service = _make_service()
        response_data = {
            "confidence": 0.85,
            "tool_ids": ["internal_document_search"],
            "middlewares": [{"type": "pii", "config": {"pii_type": "email"}}],
            "system_prompt": "pii 처리 에이전트",
            "clarifying_questions": [],
            "reasoning": "pii 포함",
        }
        history = [ConversationTurn(questions=["PII?"], answers=["네, 이메일"])]

        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=_mock_llm_response(response_data))
            MockLLM.return_value = mock_instance

            result = await service.infer("데이터 처리", history, "req-3")
            # 메시지 구성 확인
            call_args = mock_instance.ainvoke.call_args[0][0]
            user_msg = next(m for m in call_args if m["role"] == "user")
            assert "PII?" in user_msg["content"]
            assert "네, 이메일" in user_msg["content"]

        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_infer_raises_on_invalid_json(self):
        service = _make_service()
        msg = MagicMock()
        msg.content = "not valid json at all!!!"

        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=msg)
            MockLLM.return_value = mock_instance

            with pytest.raises(ValueError, match="not valid JSON"):
                await service.infer("request", [], "req-4")

    @pytest.mark.asyncio
    async def test_infer_parses_json_in_code_block(self):
        service = _make_service()
        response_data = {
            "confidence": 0.88,
            "tool_ids": ["tavily_search"],
            "middlewares": [],
            "system_prompt": "웹 검색 에이전트",
            "clarifying_questions": [],
            "reasoning": "웹 검색 필요",
        }
        msg = MagicMock()
        msg.content = f"```json\n{json.dumps(response_data)}\n```"

        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=msg)
            MockLLM.return_value = mock_instance

            result = await service.infer("웹 검색", [], "req-5")

        assert result.confidence == 0.88
        assert result.tool_ids == ["tavily_search"]

    @pytest.mark.asyncio
    async def test_infer_logs_error_and_reraises_on_exception(self):
        service = _make_service()
        with patch(
            "src.application.auto_agent_builder.agent_spec_inference_service.ChatOpenAI"
        ) as MockLLM:
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
            MockLLM.return_value = mock_instance

            with pytest.raises(RuntimeError, match="LLM down"):
                await service.infer("request", [], "req-6")

        service._logger.error.assert_called_once()
