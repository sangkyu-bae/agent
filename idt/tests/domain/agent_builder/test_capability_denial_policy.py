"""CapabilityDenialPolicy 단위 테스트.

Design Ref: worker-capability-denial-guard §3.2 / §8.2 (L1 #1~7)
Plan SC: FR-02, FR-03

워커가 자기 도구 범위를 에이전트 전체 능력으로 착각해 '어떤 도구로도 불가'라
선언한 것을 결정적으로 탐지한다. 그 다음 행동(어느 워커를 부를지)은
supervisor LLM이 판단한다 — 그래프 계약 ③.
"""
import pytest

from src.domain.agent_builder.policies import CapabilityDenialPolicy

PATTERNS = (
    "어떤 도구로도",
    "어떤 워커로도",
    "조회할 수 없도록 제한",
    "제 권한 밖",
    "제 범위 밖",
    "권한/범위 밖",
)

# 재현 케이스(런 031564e4): list_inquiries 워커가 목록 48건을 정상 반환한 뒤
# task 밖 질문에 자기 범위만 보고 답했다.
_REPRO_BODY = (
    "미답변 문의 목록은 아래와 같습니다.\n"
    + ("55089 | [엔카닷컴] 자동차 담보 대출 상품 업무 논의 요청의 건 | 기타\n" * 20)
    + "\n2. “각각 본문을 읽을 수 있나요?”에 대한 답변\n"
    "제가 접근할 수 있는 정보는 위에 보여드린 목록 수준까지만입니다.\n"
    "문의 글의 상세 본문 내용은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다.\n"
    "→ 그래서 본문 전체를 그대로 읽어서 요약해 드리는 것은 제 권한/범위 밖입니다.\n"
)


class TestDetection:

    def test_repro_body_is_detected(self):
        """재현 케이스 — 정상 데이터가 있어도 능력 부정 문구가 잡힌다."""
        assert CapabilityDenialPolicy.detect(_REPRO_BODY, PATTERNS) != ""

    def test_speaker_authority_denial_is_detected(self):
        body = "요청하신 항목을 정리했습니다.\n이 부분은 제 권한/범위 밖입니다."
        assert CapabilityDenialPolicy.detect(body, PATTERNS) != ""

    def test_legitimate_unconfirmed_answer_is_not_detected(self):
        """정당한 '확인되지 않았습니다'는 능력 부정이 아니다 — 오탐 방지."""
        body = "요청하신 2023년 데이터는 도구 결과에서 확인되지 않았습니다."
        assert CapabilityDenialPolicy.detect(body, PATTERNS) == ""

    def test_worker_scope_note_is_not_detected(self):
        """early-finish-fix D-08이 권장한 워커 범위 표기는 대상이 아니다."""
        body = "도구 결과는 위와 같습니다. 본문 조회는 이 워커의 범위 밖입니다."
        assert CapabilityDenialPolicy.detect(body, PATTERNS) == ""

    @pytest.mark.parametrize("patterns", [None, ()])
    def test_none_or_empty_patterns_disable_detection(self, patterns):
        """패턴을 비우는 것이 곧 off 스위치 — 구조적 1차 판정이 없다."""
        assert CapabilityDenialPolicy.detect(_REPRO_BODY, patterns) == ""

    def test_non_string_body_is_skipped(self):
        assert CapabilityDenialPolicy.detect(None, PATTERNS) == ""
        assert CapabilityDenialPolicy.detect([{"type": "text"}], PATTERNS) == ""

    def test_blank_pattern_entries_are_ignored(self):
        """콤마 분리 설정에서 빈 항목이 섞여도 모든 본문을 잡지 않는다."""
        assert CapabilityDenialPolicy.detect("정상 산출입니다.", ("", " ")) == ""


class TestSummaryContract:

    def test_summary_within_max_chars(self):
        summary = CapabilityDenialPolicy.detect(_REPRO_BODY, PATTERNS)
        assert 0 < len(summary) <= CapabilityDenialPolicy.MAX_SUMMARY_CHARS

    def test_summary_names_matched_pattern(self):
        """어떤 문구가 걸렸는지 드러나야 오탐 튜닝이 가능하다."""
        summary = CapabilityDenialPolicy.detect(_REPRO_BODY, PATTERNS)
        assert "어떤 도구로도" in summary

    def test_summary_is_policy_authored_not_raw_content(self):
        """§7 보안 — 고객 문의 본문(외부 콘텐츠)이 지시문 위치로 승격되지 않는다."""
        summary = CapabilityDenialPolicy.detect(_REPRO_BODY, PATTERNS)
        assert "엔카닷컴" not in summary
        assert "목록 수준까지만" not in summary
