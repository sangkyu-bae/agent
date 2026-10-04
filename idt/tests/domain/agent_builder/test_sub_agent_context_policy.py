"""SubAgentContextPolicy 단위 테스트.

Design Ref: subagent-context-scope §3.3 (R1~R8) / §8.2 (P1~P11)
Plan SC: SC-2, SC-3, SC-4

서브에이전트 입력 조립의 순수 규칙 — 원 질문·이번 턴 산출 판별, 참고자료
상한·절단, 과제 합성, 요약. 메시지 객체가 아니라 MessageView(str)만 다룬다.
"""
import pytest

from src.domain.agent_builder.sub_agent_context_policy import (
    MessageView,
    ReferenceBlock,
    SubAgentContextPolicy,
)
from src.domain.conversation.analysis_snapshot_policy import REINJECTED_MARKER

FEEDBACK = "[품질검증 실패]"


def _user(content: str) -> MessageView:
    return MessageView(role="user", name="", content=content)


def _ai(content: str, name: str = "") -> MessageView:
    return MessageView(role="ai", name=name, content=content)


@pytest.fixture
def policy() -> SubAgentContextPolicy:
    return SubAgentContextPolicy(feedback_prefixes=(FEEDBACK,))


class TestNormalizeRole:
    """R1 — 역할 정규화."""

    @pytest.mark.parametrize("raw,expected", [
        ("human", "user"), ("user", "user"),
        ("ai", "ai"), ("assistant", "ai"),
        ("system", "system"), ("tool", "tool"),
    ])
    def test_알려진_역할(self, raw, expected):
        assert SubAgentContextPolicy.normalize_role(raw) == expected

    def test_P11_문자열이_아니면_빈_역할(self):
        """MagicMock.type 같은 비문자열은 원 질문으로 잡히지 않아야 한다."""
        assert SubAgentContextPolicy.normalize_role(object()) == ""
        assert SubAgentContextPolicy.normalize_role(None) == ""


class TestFindOrigin:
    """R2/R3 — 원 질문 = 이번 턴 경계."""

    def test_P1_QG_피드백은_원_질문이_아니다(self, policy):
        views = [_user("X 조회해줘"), _ai("결과", "w1"),
                 _user(f"{FEEDBACK} 응답이 기준에 미달합니다.")]
        assert policy.find_origin_index(views) == 0

    def test_P2_이전_턴이_있으면_마지막_사용자_질문(self, policy):
        views = [_user("q1"), _ai("final1"), _user("q2"), _ai("r", "w1")]
        assert policy.find_origin_index(views) == 2

    def test_P3_재주입_사용자_메시지는_제외(self, policy):
        views = [_user("q"), _user(f"{REINJECTED_MARKER} (질문: 이전)\n데이터")]
        assert policy.find_origin_index(views) == 0

    def test_사용자_메시지가_없으면_None(self, policy):
        assert policy.find_origin_index([_ai("x", "w1")]) is None
        assert policy.find_origin_index([]) is None


class TestCollectReferences:
    """R4 — 참고자료 대상."""

    def test_P2_경계_이후의_이름있는_AI만(self, policy):
        views = [_user("q1"), _ai("old", "w0"), _user("q2"),
                 _ai("r1", "w1"), _ai("supervisor 초안"), _ai("r2", "w2")]
        refs = policy.collect_references(views, 2, "sub_a")
        assert [v.name for v in refs] == ["w1", "w2"]

    def test_P3_재주입_AI_산출은_제외(self, policy):
        views = [_user("q"), _ai(f"{REINJECTED_MARKER} (질문: p)\n...", "w1"),
                 _ai("fresh", "w2")]
        refs = policy.collect_references(views, 0, "sub_a")
        assert [v.name for v in refs] == ["w2"]

    def test_P4_자기_산출은_제외(self, policy):
        views = [_user("q"), _ai("r1", "w1"), _ai("짧음", "sub_a")]
        refs = policy.collect_references(views, 0, "sub_a")
        assert [v.name for v in refs] == ["w1"]

    def test_빈_본문은_제외(self, policy):
        views = [_user("q"), _ai("   ", "w1"), _ai("r2", "w2")]
        assert [v.name for v in policy.collect_references(views, 0, "s")] == ["w2"]

    def test_경계가_없으면_빈_목록(self, policy):
        assert policy.collect_references([_ai("r", "w1")], None, "s") == []


class TestRenderReferences:
    """R5 — 최신 우선 채움, 시간순 출력."""

    def test_P5_상한_이하는_전부_시간순(self, policy):
        refs = [_ai("A" * 100, "w1"), _ai("B" * 100, "w2"), _ai("C" * 100, "w3")]
        block = policy.render_references(refs)
        assert block.item_count == 3
        assert block.total_chars == 300
        assert block.truncated is False
        assert block.text.index("[w1 산출]") < block.text.index("[w2 산출]") \
            < block.text.index("[w3 산출]")
        assert block.text.startswith(SubAgentContextPolicy.REFERENCE_LABEL)

    def test_P6_최신만_들어가면_오래된_것은_드롭(self):
        policy = SubAgentContextPolicy(reference_max_chars=150)
        refs = [_ai("A" * 100, "w1"), _ai("B" * 100, "w2"), _ai("C" * 100, "w3")]
        block = policy.render_references(refs)
        assert block.item_count == 1
        assert "[w3 산출]" in block.text
        assert "[w1 산출]" not in block.text and "[w2 산출]" not in block.text
        assert block.truncated is True

    def test_P6_들어가는_만큼은_시간순으로_유지(self):
        policy = SubAgentContextPolicy(reference_max_chars=250)
        refs = [_ai("A" * 100, "w1"), _ai("B" * 100, "w2"), _ai("C" * 100, "w3")]
        block = policy.render_references(refs)
        assert block.item_count == 2
        assert block.text.index("[w2 산출]") < block.text.index("[w3 산출]")
        assert "[w1 산출]" not in block.text
        assert block.truncated is True

    def test_P7_최신_1건이_상한_초과면_앞부분_절단(self):
        policy = SubAgentContextPolicy(reference_max_chars=4000)
        block = policy.render_references([_ai("X" * 5000, "w1")])
        assert block.item_count == 1
        assert block.total_chars == 4000
        assert block.truncated is True
        assert ("X" * 4000 + SubAgentContextPolicy.TRUNCATED_NOTE) in block.text
        assert "X" * 4001 not in block.text

    def test_산출이_없으면_빈_블록(self, policy):
        assert policy.render_references([]) == ReferenceBlock(
            text="", item_count=0, total_chars=0, truncated=False,
        )

    def test_기본_상한은_4000(self):
        assert SubAgentContextPolicy().reference_max_chars == 4000
        assert SubAgentContextPolicy(reference_max_chars=0).reference_max_chars == 4000


class TestRetryAndTask:
    """R6/R7 — 재시도 판별과 과제 합성."""

    def test_P1_마지막이_QG_피드백이면_재시도(self, policy):
        fb = f"{FEEDBACK} 응답이 기준에 미달합니다."
        assert policy.detect_retry_feedback([_user("q"), _ai("r", "s"), _user(fb)]) == fb

    def test_마지막이_피드백이_아니면_빈_문자열(self, policy):
        assert policy.detect_retry_feedback([_user("q"), _ai("r", "w1")]) == ""
        assert policy.detect_retry_feedback([]) == ""

    def test_접두를_주입하지_않으면_재시도_판별_안함(self):
        views = [_user(f"{FEEDBACK} 미달")]
        assert SubAgentContextPolicy().detect_retry_feedback(views) == ""

    def test_P8_과제가_없으면_원_질문이_과제(self, policy):
        assert policy.compose_task("", "원 질문", "") == "[현재 작업]\n원 질문"

    def test_P9_재시도면_사유를_덧붙인다(self, policy):
        assert policy.compose_task("요약해", "q", "피드백") == (
            "[현재 작업]\n요약해\n\n[재시도 사유]\n피드백"
        )

    def test_원_질문_블록(self, policy):
        assert policy.origin_block("q") == "[원 질문]\nq"


class TestSummarize:
    """R8 — 요약에는 길이·개수만, 본문 값은 없다."""

    def test_P10_형식(self, policy):
        ref = ReferenceBlock(text="비밀 본문", item_count=2, total_chars=1830,
                             truncated=True)
        out = policy.summarize(has_origin=True, ref=ref, retry=False, fallback=False)
        assert out == "서브에이전트 입력: 원질문 O / 참고자료 2건 1830자 (절단) / 재시도 X"
        assert "비밀" not in out

    def test_절단_없으면_표기_없음(self, policy):
        ref = ReferenceBlock(text="", item_count=0, total_chars=0, truncated=False)
        out = policy.summarize(has_origin=False, ref=ref, retry=True, fallback=False)
        assert out == "서브에이전트 입력: 원질문 X / 참고자료 0건 0자 / 재시도 O"

    def test_fallback(self, policy):
        ref = ReferenceBlock(text="", item_count=0, total_chars=0, truncated=False)
        out = policy.summarize(has_origin=False, ref=ref, retry=False, fallback=True)
        assert out == "서브에이전트 입력: 레거시(마지막 메시지)"
