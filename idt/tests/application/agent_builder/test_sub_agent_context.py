"""SubAgentContextStrategy / TaskWithOriginStrategy 단위 테스트.

Design Ref: subagent-context-scope §3.2/§3.4 / §8.3 (S1~S7)
Plan SC: SC-1, SC-2, SC-5

부모 SupervisorState → 서브에이전트 초기 messages 조립. 규칙은 domain
SubAgentContextPolicy가, 메시지 객체 해석·조립은 이 전략이 맡는다.
"""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import (
    QUALITY_FEEDBACK_PREFIX,
    is_search_result,
)
from src.application.agent_builder.sub_agent_context import (
    SubAgentContextStrategy,
    SubAgentInput,
    TaskWithOriginStrategy,
    resolve_strategy,
    to_message_views,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.sub_agent_context_policy import (
    MessageView,
    SubAgentContextPolicy,
)

SELF = "sub_agent_요약_0"
FB = f"{QUALITY_FEEDBACK_PREFIX} 응답이 기준에 미달합니다. (재시도 1/2)"


def _state(messages: list, task: str = "") -> dict:
    return {"messages": messages, "worker_task": task,
            "token_usage": 0, "token_limit": 8000}


def _contents(result: SubAgentInput) -> list[str]:
    return [m["content"] for m in result.messages]


class TestToMessageViews:
    def test_LangChain_메시지와_dict를_정규화(self):
        views = to_message_views([
            HumanMessage(content="q"),
            AIMessage(content="r", name="w1"),
            {"role": "user", "content": "fb"},
        ])
        assert views == [
            MessageView(role="user", name="", content="q"),
            MessageView(role="ai", name="w1", content="r"),
            MessageView(role="user", name="", content="fb"),
        ]

    def test_MagicMock은_역할도_이름도_없다(self):
        msg = MagicMock()
        msg.content = "작업"
        assert to_message_views([msg]) == [MessageView(role="", name="", content="작업")]

    def test_비문자열_content는_str_변환(self):
        views = to_message_views([HumanMessage(content=[{"type": "text", "text": "x"}])])
        assert views[0].role == "user"
        assert "x" in views[0].content


class TestTaskWithOriginStrategy:
    def test_S1_첫_라우팅은_원_질문과_현재_작업(self):
        out = TaskWithOriginStrategy().build(
            _state([HumanMessage(content="X 조회해서 요약해줘")], task="X 3줄 요약"),
            SELF,
        )
        assert _contents(out) == [
            "[원 질문]\nX 조회해서 요약해줘",
            "[현재 작업]\nX 3줄 요약",
        ]
        assert all(m["role"] == "user" for m in out.messages)
        assert out.summary == "서브에이전트 입력: 원질문 O / 참고자료 0건 0자 / 재시도 X"

    def test_S2_중간_라우팅은_참고자료를_싣고_마지막이_과제(self):
        out = TaskWithOriginStrategy().build(
            _state([HumanMessage(content="q"), AIMessage(content="w1 결과", name="w1")],
                   task="요약"),
            SELF,
        )
        contents = _contents(out)
        assert len(contents) == 3
        assert contents[0] == "[원 질문]\nq"
        assert contents[1].startswith(SubAgentContextPolicy.REFERENCE_LABEL)
        assert "[w1 산출]\nw1 결과" in contents[1]
        assert contents[2] == "[현재 작업]\n요약"
        assert "참고자료 1건 5자" in out.summary

    def test_S3_QG_재시도는_원_과제와_사유를_함께(self):
        out = TaskWithOriginStrategy().build(
            _state([
                HumanMessage(content="q"),
                AIMessage(content="w1 결과", name="w1"),
                AIMessage(content="짧음", name=SELF),
                HumanMessage(content=FB),
            ], task="요약"),
            SELF,
        )
        contents = _contents(out)
        assert contents[-1] == f"[현재 작업]\n요약\n\n[재시도 사유]\n{FB}"
        assert "짧음" not in contents[1]  # 자기 실패 산출은 참고자료에서 제외
        assert contents[0] == "[원 질문]\nq"
        assert out.summary.endswith("재시도 O")

    def test_공백_worker_id의_자기_산출도_제외(self):
        """FR-12 — 저장된 id에 공백이 있으면 메시지 이름은 치환돼 있다."""
        spaced = "sub_agent_[L3] 요약 서브_0"
        out = TaskWithOriginStrategy().build(
            _state([
                HumanMessage(content="q"),
                AIMessage(content="w1 결과", name="w1"),
                AIMessage(content="자기 산출", name="sub_agent_[L3]_요약_서브_0"),
            ], task="요약"),
            spaced,
        )
        assert "자기 산출" not in _contents(out)[1]
        assert "w1 결과" in _contents(out)[1]

    def test_S4_과제가_없으면_원_질문이_과제_원질문_블록_생략(self):
        out = TaskWithOriginStrategy().build(
            _state([HumanMessage(content="q")], task=""), SELF,
        )
        assert _contents(out) == ["[현재 작업]\nq"]

    def test_S5_원질문도_과제도_없으면_현행_입력(self):
        legacy = MagicMock()
        legacy.content = "문서를 분석해주세요"
        out = TaskWithOriginStrategy().build(_state([legacy]), SELF)
        assert out.messages == [{"role": "user", "content": "문서를 분석해주세요"}]
        assert out.summary == "서브에이전트 입력: 레거시(마지막 메시지)"

    def test_S5_worker_task_키가_없어도_동작(self):
        legacy = MagicMock()
        legacy.content = "작업"
        out = TaskWithOriginStrategy().build(
            {"messages": [legacy], "token_usage": 0, "token_limit": 8000}, SELF,
        )
        assert out.messages == [{"role": "user", "content": "작업"}]

    def test_원질문_없이_과제만_있으면_과제만(self):
        legacy = MagicMock()
        legacy.content = "무시됨"
        out = TaskWithOriginStrategy().build(_state([legacy], task="T"), SELF)
        assert _contents(out) == ["[현재 작업]\nT"]

    def test_S6_출력은_검색결과로_식별되지_않는다(self):
        """참고자료가 자식의 강제 라우팅 규약(is_search_result)에 걸리지 않음."""
        out = TaskWithOriginStrategy().build(
            _state([HumanMessage(content="q"),
                    AIMessage(content="[w1 검색결과]\n데이터", name="w1")],
                   task="분석"),
            SELF,
        )
        assert not any(is_search_result(m) for m in out.messages)

    def test_주입한_Policy의_상한을_따른다(self):
        strategy = TaskWithOriginStrategy(
            policy=SubAgentContextPolicy(
                feedback_prefixes=(QUALITY_FEEDBACK_PREFIX,), reference_max_chars=3,
            )
        )
        out = strategy.build(
            _state([HumanMessage(content="q"), AIMessage(content="ABCDE", name="w1")],
                   task="t"),
            SELF,
        )
        assert "ABC" + SubAgentContextPolicy.TRUNCATED_NOTE in _contents(out)[1]
        assert "(절단)" in out.summary


class TestResolveStrategy:
    def test_S7_현재는_항상_기본_전략(self):
        default = TaskWithOriginStrategy()
        worker = WorkerDefinition(
            tool_id="sub_agent_abc", worker_id=SELF, description="d",
            sort_order=0, worker_type="sub_agent", ref_agent_id="abc",
        )
        assert resolve_strategy(worker, default) is default

    def test_Protocol을_만족하는_대역도_전략으로_쓸_수_있다(self):
        class Fake:
            def build(self, state, worker_id):
                return SubAgentInput(messages=[{"role": "user", "content": "x"}],
                                     summary="s")

        strategy: SubAgentContextStrategy = Fake()
        assert strategy.build({}, SELF).summary == "s"
        assert isinstance(TaskWithOriginStrategy(), SubAgentContextStrategy)
