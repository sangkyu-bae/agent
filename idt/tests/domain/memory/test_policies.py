"""MemoryPolicy 단위 테스트 (agent-memory Design §3-2).

순수 규칙만 검증 — DB/LLM 미사용.
"""
from datetime import datetime, timedelta

import pytest

from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.domain.memory.policies import MemoryPolicy


def _memory(
    mem_type: MemoryType = MemoryType.PROFILE,
    content: str = "여신 심사팀 소속",
    updated_at: datetime | None = None,
    memory_id: int | None = 1,
) -> Memory:
    return Memory(
        id=memory_id,
        scope=MemoryScope.USER,
        user_id="user-1",
        tier=0,
        mem_type=mem_type,
        content=content,
        updated_at=updated_at or datetime(2026, 7, 18, 12, 0, 0),
    )


class TestValidateContent:
    def test_정상_내용은_통과(self):
        MemoryPolicy.validate_content("근거 조문 번호 인용 선호")

    def test_최대_길이_경계값_통과(self):
        MemoryPolicy.validate_content("가" * MemoryPolicy.CONTENT_MAX)

    def test_빈_문자열_거부(self):
        with pytest.raises(ValueError):
            MemoryPolicy.validate_content("")

    def test_공백만_있으면_거부(self):
        with pytest.raises(ValueError):
            MemoryPolicy.validate_content("   ")

    def test_상한_초과_거부(self):
        with pytest.raises(ValueError):
            MemoryPolicy.validate_content("가" * (MemoryPolicy.CONTENT_MAX + 1))


class TestValidateActiveCount:
    def test_상한_미만이면_통과(self):
        MemoryPolicy.validate_active_count(current_count=29, max_count=30)

    def test_상한_도달이면_거부(self):
        with pytest.raises(ValueError, match="상한"):
            MemoryPolicy.validate_active_count(current_count=30, max_count=30)

    def test_상한_초과이면_거부(self):
        with pytest.raises(ValueError, match="상한"):
            MemoryPolicy.validate_active_count(current_count=31, max_count=30)


class TestSortForInjection:
    def test_타입_우선순위_정렬(self):
        episode = _memory(MemoryType.EPISODE, memory_id=1)
        profile = _memory(MemoryType.PROFILE, memory_id=2)
        preference = _memory(MemoryType.PREFERENCE, memory_id=3)
        term = _memory(MemoryType.DOMAIN_TERM, memory_id=4)

        ordered = MemoryPolicy.sort_for_injection([episode, preference, term, profile])

        assert [m.mem_type for m in ordered] == [
            MemoryType.PROFILE,
            MemoryType.DOMAIN_TERM,
            MemoryType.PREFERENCE,
            MemoryType.EPISODE,
        ]

    def test_동일_타입은_최신순(self):
        base = datetime(2026, 7, 18, 12, 0, 0)
        old = _memory(MemoryType.PROFILE, updated_at=base, memory_id=1)
        new = _memory(MemoryType.PROFILE, updated_at=base + timedelta(hours=1), memory_id=2)

        ordered = MemoryPolicy.sort_for_injection([old, new])

        assert [m.id for m in ordered] == [2, 1]

    def test_원본_목록_불변(self):
        items = [_memory(MemoryType.EPISODE, memory_id=1), _memory(MemoryType.PROFILE, memory_id=2)]
        MemoryPolicy.sort_for_injection(items)
        assert [m.id for m in items] == [1, 2]


class TestTruncateToBudget:
    def test_예산_내면_전부_포함_절단_없음(self):
        items = [_memory(content="가" * 100, memory_id=i) for i in range(3)]

        included, truncated = MemoryPolicy.truncate_to_budget(items, token_cap=800)

        assert len(included) == 3
        assert truncated is False

    def test_예산_초과분_절단_및_플래그(self):
        items = [_memory(content="가" * 300, memory_id=i) for i in range(4)]  # 총 1200자

        included, truncated = MemoryPolicy.truncate_to_budget(items, token_cap=800)

        assert len(included) == 2  # 300+300=600 ≤ 800, 900 > 800에서 중단
        assert truncated is True

    def test_정렬_순서를_보존한_앞에서부터_포함(self):
        items = [
            _memory(content="가" * 500, memory_id=1),
            _memory(content="나" * 500, memory_id=2),
        ]

        included, truncated = MemoryPolicy.truncate_to_budget(items, token_cap=800)

        assert [m.id for m in included] == [1]
        assert truncated is True

    def test_빈_목록은_빈_결과(self):
        included, truncated = MemoryPolicy.truncate_to_budget([], token_cap=800)
        assert included == []
        assert truncated is False


class TestEntityDefaults:
    def test_phase1_수동_등록_기본값(self):
        memory = _memory()
        assert memory.status == MemoryStatus.ACTIVE
        assert memory.confidence == 100
        assert memory.source_run_id is None


# ── Phase 2: 추출·승인 게이트 정책 (agent-memory-extraction) ──────────


def _pending(memory_id: int = 1) -> Memory:
    m = _memory(memory_id=memory_id)
    m.status = MemoryStatus.PENDING
    return m


class TestValidateTransition:
    def test_pending은_전이_가능(self):
        MemoryPolicy.validate_transition(_pending())

    def test_active는_전이_불가(self):
        with pytest.raises(ValueError, match="승인 대기"):
            MemoryPolicy.validate_transition(_memory())

    def test_rejected는_전이_불가(self):
        m = _memory()
        m.status = MemoryStatus.REJECTED
        with pytest.raises(ValueError, match="승인 대기"):
            MemoryPolicy.validate_transition(m)


class TestClampConfidence:
    def test_범위_내_값은_유지(self):
        assert MemoryPolicy.clamp_confidence(70) == 70

    def test_상한_초과는_100(self):
        assert MemoryPolicy.clamp_confidence(250) == 100

    def test_음수는_0(self):
        assert MemoryPolicy.clamp_confidence(-5) == 0


class _Candidate:
    """content 속성만 갖는 duck-typed 후보 (domain은 application 타입 미참조)."""

    def __init__(self, content: str) -> None:
        self.content = content


class TestDedupCandidates:
    def test_기존_content와_일치하면_제거(self):
        result = MemoryPolicy.dedup_candidates(
            [_Candidate("여신 심사팀 소속"), _Candidate("새 정보")],
            existing_contents={"여신 심사팀 소속"},
        )
        assert [c.content for c in result] == ["새 정보"]

    def test_공백_차이는_동일_취급(self):
        result = MemoryPolicy.dedup_candidates(
            [_Candidate("  여신 심사팀 소속  ")],
            existing_contents={"여신 심사팀 소속"},
        )
        assert result == []

    def test_후보_내_중복도_제거(self):
        result = MemoryPolicy.dedup_candidates(
            [_Candidate("같은 내용"), _Candidate("같은 내용")],
            existing_contents=set(),
        )
        assert len(result) == 1

    def test_빈_입력은_빈_결과(self):
        assert MemoryPolicy.dedup_candidates([], existing_contents=set()) == []
