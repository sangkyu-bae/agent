"""ActionToolConfig VO 단위 테스트.

Design Ref: action-category-compose-node §3.1
  - draft_arg_key: 초안을 넣을 도구 인자 키. 빈 문자열 = 관례 키 자동 탐색
  - WorkerDefinition.tool_config(dict)와 asdict 왕복
  - 알 수 없는 키는 무시(다른 도구 설정과 dict 공유 허용, D-10 하위호환)
"""
import pytest

from src.domain.agent_builder.action_tool_config import ActionToolConfig


class TestActionToolConfigConstruction:
    def test_default_is_empty_key(self):
        cfg = ActionToolConfig()
        assert cfg.draft_arg_key == ""

    def test_explicit_key(self):
        cfg = ActionToolConfig(draft_arg_key="body")
        assert cfg.draft_arg_key == "body"

    def test_rejects_non_string_key(self):
        with pytest.raises(ValueError):
            ActionToolConfig(draft_arg_key=123)  # type: ignore[arg-type]

    def test_is_frozen(self):
        cfg = ActionToolConfig(draft_arg_key="body")
        with pytest.raises(Exception):
            cfg.draft_arg_key = "content"  # type: ignore[misc]


class TestActionToolConfigFromToolConfig:
    def test_none_yields_default(self):
        assert ActionToolConfig.from_tool_config(None) == ActionToolConfig()

    def test_empty_dict_yields_default(self):
        assert ActionToolConfig.from_tool_config({}) == ActionToolConfig()

    def test_reads_draft_arg_key(self):
        cfg = ActionToolConfig.from_tool_config({"draft_arg_key": "content"})
        assert cfg.draft_arg_key == "content"

    def test_ignores_unknown_keys(self):
        """D-10: fixed_args 등 미래 키·다른 도구 키가 섞여 있어도 깨지지 않는다."""
        cfg = ActionToolConfig.from_tool_config(
            {"draft_arg_key": "body", "type_id": "x", "fixed_args": {"a": 1}}
        )
        assert cfg.draft_arg_key == "body"

    def test_null_value_becomes_empty(self):
        cfg = ActionToolConfig.from_tool_config({"draft_arg_key": None})
        assert cfg.draft_arg_key == ""


class TestActionToolConfigModelDump:
    def test_round_trip(self):
        cfg = ActionToolConfig(draft_arg_key="body")
        assert ActionToolConfig.from_tool_config(cfg.model_dump()) == cfg

    def test_dump_shape(self):
        assert ActionToolConfig(draft_arg_key="body").model_dump() == {
            "draft_arg_key": "body"
        }
