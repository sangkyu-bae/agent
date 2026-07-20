"""MemoryContextAssembler 단위 테스트 (agent-memory Design §3-3).

FR-05 절단 로그 · FR-06 빈 헤더 금지 · FR-07 실패 격리 · FR-09 보수 지침 렌더.
RunScopedWikiSearch 테스트와 동일한 session_factory/repo_builder 주입 패턴.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.application.memory.context_assembler import MemoryContextAssembler
from src.domain.memory.entity import Memory, MemoryScope, MemoryType


def _memory(memory_id, mem_type, content, updated_at=None, scope=MemoryScope.USER) -> Memory:
    return Memory(
        id=memory_id, scope=scope, user_id="u1" if scope == MemoryScope.USER else "d1",
        tier=0, mem_type=mem_type, content=content,
        updated_at=updated_at or datetime(2026, 7, 18, 12, 0, 0),
    )


class _SessionCtx:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        self._counter["opened"] += 1
        return MagicMock()

    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make(memories=None, token_cap=800, repo_error=None, org_memories=None):
    counter = {"opened": 0, "closed": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    if repo_error is not None:
        repo.find_active_by_user = AsyncMock(side_effect=repo_error)
    else:
        repo.find_active_by_user = AsyncMock(return_value=memories or [])
    # 실 저장소처럼 빈 부서 리스트면 [] 반환 (assembler가 dept_ids 없으면 []로 호출)
    async def _find_org(dept_ids, request_id):
        return list(org_memories or []) if dept_ids else []

    repo.find_active_by_departments = AsyncMock(side_effect=_find_org)

    logger = MagicMock()
    assembler = MemoryContextAssembler(
        session_factory=session_factory,
        logger=logger,
        token_cap=token_cap,
        repo_builder=lambda session: repo,
    )
    return assembler, logger, counter


class TestBuildBlock:
    async def test_렌더_형식_헤더와_보수_지침과_타입_라벨(self):
        assembler, _, _ = _make([
            _memory(1, MemoryType.PROFILE, "여신 심사팀 소속"),
            _memory(2, MemoryType.DOMAIN_TERM, "'한도'는 동일인 여신한도"),
            _memory(3, MemoryType.PREFERENCE, "근거 조문 번호 인용 선호"),
            _memory(4, MemoryType.EPISODE, "지난달 규정 개정 문의함"),
        ])

        block = await assembler.build_block("u1", "req-1")

        assert block.startswith("[사용자 메모리]")
        assert "확인하세요" in block  # FR-09 보수 지침
        assert "- (프로필) 여신 심사팀 소속" in block
        assert "- (용어) '한도'는 동일인 여신한도" in block
        assert "- (선호) 근거 조문 번호 인용 선호" in block
        assert "- (참고) 지난달 규정 개정 문의함" in block
        assert block.endswith("---\n\n")  # user-context 블록과 동일 구분자

    async def test_우선순위_정렬이_반영된다(self):
        assembler, _, _ = _make([
            _memory(1, MemoryType.EPISODE, "에피소드"),
            _memory(2, MemoryType.PROFILE, "프로필"),
        ])

        block = await assembler.build_block("u1", "req-1")

        assert block.index("(프로필)") < block.index("(참고)")

    async def test_캡_초과분_절단_및_debug_로그(self):
        assembler, logger, _ = _make(
            [
                _memory(1, MemoryType.PROFILE, "AAA" * 100),
                _memory(2, MemoryType.PROFILE, "BBB" * 100, updated_at=datetime(2026, 7, 17)),
                _memory(3, MemoryType.PROFILE, "CCC" * 100, updated_at=datetime(2026, 7, 16)),
            ],
            token_cap=700,
        )

        block = await assembler.build_block("u1", "req-1")

        assert "AAA" in block and "BBB" in block
        assert "CCC" not in block
        logger.debug.assert_called_once()  # FR-05

    async def test_0건이면_빈_문자열_헤더_금지(self):
        assembler, _, _ = _make([])

        block = await assembler.build_block("u1", "req-1")

        assert block == ""  # FR-06

    async def test_개인과_부서_메모리를_병합_렌더(self):
        assembler, _, _ = _make(
            memories=[_memory(1, MemoryType.PROFILE, "여신 심사팀 소속")],
            org_memories=[
                _memory(2, MemoryType.DOMAIN_TERM, "'한도'는 동일인 여신한도",
                        scope=MemoryScope.ORG),
            ],
        )

        block = await assembler.build_block("u1", "req-1", dept_ids=["d1"])

        assert "여신 심사팀 소속" in block
        assert "'한도'는 동일인 여신한도" in block
        assert "(부서 공유)" in block  # FR-06 출처 라벨

    async def test_개인이_부서보다_먼저_렌더(self):
        assembler, _, _ = _make(
            memories=[_memory(1, MemoryType.EPISODE, "개인 참고사항")],
            org_memories=[
                _memory(2, MemoryType.PROFILE, "부서 프로필", scope=MemoryScope.ORG),
            ],
        )

        block = await assembler.build_block("u1", "req-1", dept_ids=["d1"])

        assert block.index("개인 참고사항") < block.index("부서 프로필")

    async def test_dept_ids_없으면_개인만_렌더_회귀(self):
        assembler, _, _ = _make(
            memories=[_memory(1, MemoryType.PROFILE, "개인만")],
            org_memories=[_memory(2, MemoryType.PROFILE, "부서", scope=MemoryScope.ORG)],
        )

        block = await assembler.build_block("u1", "req-1")  # dept_ids 미전달

        assert "개인만" in block
        assert "부서" not in block

    async def test_개인과_부서_content_중복은_개인_유지(self):
        assembler, _, _ = _make(
            memories=[_memory(1, MemoryType.PROFILE, "공통 내용")],
            org_memories=[_memory(2, MemoryType.PROFILE, "공통 내용", scope=MemoryScope.ORG)],
        )

        block = await assembler.build_block("u1", "req-1", dept_ids=["d1"])

        assert block.count("공통 내용") == 1
        assert "(부서 공유)" not in block  # 개인이 우선 남음

    async def test_저장소_예외_시_빈_문자열과_warning(self):
        assembler, logger, _ = _make(repo_error=RuntimeError("db down"))

        block = await assembler.build_block("u1", "req-1")

        assert block == ""  # FR-07 격리
        logger.warning.assert_called_once()

    async def test_세션은_호출마다_열고_닫는다(self):
        assembler, _, counter = _make([_memory(1, MemoryType.PROFILE, "내용")])

        await assembler.build_block("u1", "req-1")
        await assembler.build_block("u1", "req-2")

        assert counter["opened"] == 2
        assert counter["closed"] == 2
