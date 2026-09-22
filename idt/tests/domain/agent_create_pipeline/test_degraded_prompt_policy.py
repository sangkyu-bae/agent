"""DegradedPromptPolicy — prompt-fallback-visibility Design §4-1 (T-01~T-05).

"degraded 로 생성된 프롬프트를 편집 없이 그대로 저장하려는가"를 판정한다.

**왜 내용 비교인가** (Design §2-3 / D3):
저장(`POST /api/v1/agents`)이 편집본 버전 append(`linkPromptSession`)보다
먼저 일어나므로, 저장 시점에는 `source='human'` 버전이 아직 없다. 따라서
"편집했는가"는 저장된 원본과 제출본을 대조해서만 알 수 있다.

**Plan §7-2 "폴백 문자열 매칭 금지"와 다르다**: 폴백 상수와 대조하는 게 아니라
*그 세션이 생성한 그 버전*과 대조한다. 한 글자 수정이 "편집함"이 되는 것은
의도된 동작이다 (FR-05).
"""
import pytest

from src.domain.agent_create_pipeline.policies import (
    DegradedPromptPolicy,
    PipelinePolicy,
)

_PROMPT = "## Role and Identity\n사용자의 요청을 처리하는 범용 에이전트입니다."


class TestNotDegraded:
    """T-01 — degraded 가 아니면 내용과 무관하게 막지 않는다."""

    @pytest.mark.parametrize("submitted", [_PROMPT, "완전히 다른 프롬프트", ""])
    def test_never_blocks(self, submitted: str) -> None:
        assert DegradedPromptPolicy.blocks(
            version_degraded=False,
            stored_assembled=_PROMPT,
            submitted_prompt=submitted,
        ) is False


class TestDegradedUnedited:
    """T-02 — degraded 이고 내용이 같으면 막는다."""

    def test_blocks_identical(self) -> None:
        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=_PROMPT,
            submitted_prompt=_PROMPT,
        ) is True


class TestDegradedEdited:
    """T-03 — degraded 여도 사용자가 고쳤으면 허용한다 (FR-05)."""

    def test_allows_edited(self) -> None:
        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=_PROMPT,
            submitted_prompt=_PROMPT + "\n- 추가한 규칙",
        ) is False

    def test_single_char_edit_counts_as_edit(self) -> None:
        """한 글자만 고쳐도 편집이다 — 의도된 동작 (Plan §7-2 와의 차이)."""
        edited = _PROMPT.replace("범용", "범용!")
        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=_PROMPT,
            submitted_prompt=edited,
        ) is False


class TestClampEquivalence:
    """T-04 — ★ Design §7-1 최대 위험 고정.

    위저드가 받는 `assembled_prompt` 는 `PipelinePolicy.clamp_prompt()` 를 거친
    값이지만(use_case.py:348-349), DB 의 `assembled` 는 **원본**이다.
    단순 `==` 는 상한 초과 프롬프트에서 항상 "편집함"으로 오판해 게이트를
    무력화한다.
    """

    def test_long_prompt_clamped_submission_still_blocked(self) -> None:
        limit = PipelinePolicy.PROMPT_MAX_CHARS
        original = "가" * (limit + 500)  # DB 원본 — 상한 초과
        clamped, _ = PipelinePolicy.clamp_prompt(original)  # 위저드가 받은 값
        assert len(clamped) == limit
        assert clamped != original  # 단순 == 라면 여기서 "편집함"으로 샌다

        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=original,
            submitted_prompt=clamped,
        ) is True

    def test_edit_beyond_limit_on_long_prompt_is_invisible(self) -> None:
        """상한 너머에서만 다른 편집은 clamp 후 동일하므로 막힌다.

        제출본은 서버 스키마(max_length)에서 이미 상한으로 잘리므로, 상한 뒤의
        차이는 저장되지 않는 차이다 — 막는 게 맞다.
        """
        limit = PipelinePolicy.PROMPT_MAX_CHARS
        original = "가" * (limit + 10)
        submitted = "가" * limit + "나" * 10  # 상한 뒤만 다름

        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=original,
            submitted_prompt=submitted,
        ) is True


class TestWhitespaceNormalization:
    """T-05 — 앞뒤 공백 차이는 편집이 아니다.

    textarea 왕복·trim 처리 차이로 생기는 공백은 사용자의 의도가 아니다.
    """

    @pytest.mark.parametrize(
        "submitted",
        [f"  {_PROMPT}", f"{_PROMPT}\n\n", f"\n{_PROMPT}\t"],
    )
    def test_outer_whitespace_ignored(self, submitted: str) -> None:
        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=_PROMPT,
            submitted_prompt=submitted,
        ) is True

    def test_inner_whitespace_is_an_edit(self) -> None:
        """내부 공백 변경은 편집으로 본다 — 줄바꿈 추가 등은 의미가 있다."""
        edited = _PROMPT.replace("\n", "\n\n")
        assert DegradedPromptPolicy.blocks(
            version_degraded=True,
            stored_assembled=_PROMPT,
            submitted_prompt=edited,
        ) is False
