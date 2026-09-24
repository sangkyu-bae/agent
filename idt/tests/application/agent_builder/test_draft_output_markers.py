"""초안 산출 규약 단위 테스트 — format_draft_output / is_draft_output / split_draft_output.

Design Ref: action-category-compose-node §3.4 / D-06
  - 워커 산출은 AIMessage 1건. 본문은 "[w 초안]" / "[w 집행결과]" 두 구획.
  - is_draft_output은 첫 줄 정확 일치로 판정 — 본문에 '초안' 단어가 있어도 오탐 없음.
  - split_draft_output은 '마지막' 집행결과 줄을 경계로 쓴다 — 초안 본문 안에
    같은 줄이 있어도 구획이 깨지지 않는다.
  - search 규약(is_search_result)과 서로 배타, is_worker_output에는 포함.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import (
    DRAFT_OUTCOME_MARKER,
    DRAFT_OUTPUT_MARKER,
    format_draft_output,
    format_search_result,
    is_draft_output,
    is_search_result,
    is_worker_output,
    split_draft_output,
)

W = "mail_sender"


def _msg(content: str, name: str | None = W) -> AIMessage:
    return AIMessage(content=content, name=name)


class TestFormat:
    def test_layout(self):
        text = format_draft_output(W, "안녕하세요", "발송 완료")
        assert text == (
            f"[{W} {DRAFT_OUTPUT_MARKER}]\n안녕하세요\n\n"
            f"[{W} {DRAFT_OUTCOME_MARKER}]\n발송 완료"
        )

    def test_markers_are_distinct_words(self):
        assert DRAFT_OUTPUT_MARKER != DRAFT_OUTCOME_MARKER


class TestIsDraftOutput:
    def test_true_for_formatted_message(self):
        assert is_draft_output(_msg(format_draft_output(W, "d", "o")))

    def test_false_without_name(self):
        assert not is_draft_output(_msg(format_draft_output(W, "d", "o"), name=None))

    def test_false_when_name_mismatch(self):
        """첫 줄의 worker_id와 AIMessage.name이 다르면 초안이 아니다."""
        assert not is_draft_output(_msg(format_draft_output("other", "d", "o")))

    def test_false_for_search_result(self):
        assert not is_draft_output(_msg(format_search_result(W, "본문")))

    def test_false_when_word_appears_in_body_only(self):
        assert not is_draft_output(_msg(f"이것은 {DRAFT_OUTPUT_MARKER} 단어를 포함한 일반 답변"))

    def test_false_for_dict_and_human(self):
        assert not is_draft_output({"role": "assistant", "content": "x"})
        assert not is_draft_output(HumanMessage(content=format_draft_output(W, "d", "o")))

    def test_exclusive_with_search_result(self):
        draft = _msg(format_draft_output(W, "d", "o"))
        assert is_draft_output(draft) and not is_search_result(draft)

    def test_is_worker_output(self):
        """final_answer·generator의 근거 분류가 초안 메시지를 워커 산출로 본다."""
        assert is_worker_output(_msg(format_draft_output(W, "d", "o")))


class TestSplitDraftOutput:
    def test_round_trip(self):
        msg = _msg(format_draft_output(W, "첫 줄\n\n둘째 줄", "ok"))
        assert split_draft_output(msg) == (W, "첫 줄\n\n둘째 줄", "ok")

    def test_preserves_whitespace_and_brackets(self):
        draft = "  들여쓰기  \n[대괄호] 포함\n끝  "
        msg = _msg(format_draft_output(W, draft, "결과"))
        assert split_draft_output(msg)[1] == draft

    def test_last_outcome_marker_is_boundary(self):
        """초안 안에 '[w 집행결과]' 줄이 있어도 마지막 출현이 경계."""
        tricky = f"본문 중간에\n[{W} {DRAFT_OUTCOME_MARKER}]\n가 들어감"
        msg = _msg(format_draft_output(W, tricky, "진짜 결과"))
        assert split_draft_output(msg) == (W, tricky, "진짜 결과")

    def test_empty_draft(self):
        msg = _msg(format_draft_output(W, "", "초안 작성 실패: x"))
        assert split_draft_output(msg) == (W, "", "초안 작성 실패: x")

    def test_none_for_non_draft(self):
        assert split_draft_output(_msg(format_search_result(W, "본문"))) is None
        assert split_draft_output(_msg("그냥 답변")) is None

    def test_multiline_outcome(self):
        msg = _msg(format_draft_output(W, "d", "줄1\n줄2"))
        assert split_draft_output(msg)[2] == "줄1\n줄2"
