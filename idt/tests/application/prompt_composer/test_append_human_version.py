"""AppendHumanVersionUseCase 단위 테스트.

agent-create-wizard Design Ref: §3.4 / §4.5.

핵심 계약 3개:
- 세션 소유권 검사가 **먼저** — 타인/부재는 append 전에 예외 (→ 404).
- 저장되는 버전의 `source` 는 항상 `human` (LLM 경로와 구분).
- `sections` 는 빈 구조 — 사람 편집본은 섹션 분해가 없다. LLM 생성물이
  아니므로 `degraded=False` / `elapsed_ms=0` 이다.
"""
import pytest
from src.application.prompt_composer.append_human_version_use_case import (
    AppendHumanVersionUseCase,
)
from src.application.prompt_composer.errors import PromptSessionNotFoundError
from src.domain.prompt_composer.schemas import PROMPT_SOURCE_HUMAN


class FakeRepository:
    """PromptRepositoryPort 대역 — append_version 호출을 기록한다."""

    def __init__(self, session_found: bool = True):
        self.session_found = session_found
        self.appends: list[dict] = []

    async def find_session(self, session_id, user_id):
        return object() if self.session_found else None

    async def append_version(
        self, session_id, prompt, intent_snapshot, tool_ids, source="llm"
    ):
        self.appends.append(
            {
                "session_id": session_id,
                "prompt": prompt,
                "intent_snapshot": intent_snapshot,
                "tool_ids": tool_ids,
                "source": source,
            }
        )
        return "v-new", len(self.appends) + 1


class FakeLogger:
    def __init__(self):
        self.records: list[tuple[str, dict]] = []

    def info(self, message, **kwargs):
        self.records.append((message, kwargs))

    def warning(self, message, **kwargs):
        self.records.append((message, kwargs))

    def error(self, message, **kwargs):
        self.records.append((message, kwargs))


def _use_case(repo: FakeRepository) -> AppendHumanVersionUseCase:
    return AppendHumanVersionUseCase(repository=repo, logger=FakeLogger())


# ── 정상 경로 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_appends_version_with_human_source():
    repo = FakeRepository()
    result = await _use_case(repo).append(
        session_id="s1",
        user_id="7",
        assembled="사람이 고친 프롬프트",
        tool_ids=("internal:hybrid_search",),
    )
    assert result.session_id == "s1"
    assert result.version_id == "v-new"
    assert result.source == PROMPT_SOURCE_HUMAN
    assert repo.appends[0]["source"] == PROMPT_SOURCE_HUMAN


@pytest.mark.asyncio
async def test_persists_edited_text_verbatim():
    repo = FakeRepository()
    await _use_case(repo).append(
        session_id="s1", user_id="7", assembled="  줄바꿈\n포함  ", tool_ids=()
    )
    assert repo.appends[0]["prompt"].assembled == "  줄바꿈\n포함  "


@pytest.mark.asyncio
async def test_stores_empty_sections_and_zero_observability():
    """사람 편집본은 LLM 산출물이 아니다 — 섹션 분해도 관측치도 없다."""
    repo = FakeRepository()
    await _use_case(repo).append(
        session_id="s1", user_id="7", assembled="p", tool_ids=()
    )
    prompt = repo.appends[0]["prompt"]
    assert prompt.sections.purpose == ""
    assert prompt.sections.roles == ()
    assert prompt.sections.tool_guides == ()
    assert prompt.sections.principles == ()
    assert prompt.degraded is False
    assert prompt.reason is None
    assert prompt.elapsed_ms == 0


@pytest.mark.asyncio
async def test_intent_snapshot_is_not_carried_over():
    """편집본의 근거는 사람이다 — 이전 버전의 의도를 복사해 오도하지 않는다."""
    repo = FakeRepository()
    await _use_case(repo).append(
        session_id="s1", user_id="7", assembled="p", tool_ids=()
    )
    assert repo.appends[0]["intent_snapshot"] is None


@pytest.mark.asyncio
async def test_tool_ids_are_preserved_in_order():
    repo = FakeRepository()
    await _use_case(repo).append(
        session_id="s1",
        user_id="7",
        assembled="p",
        tool_ids=("b", "a", "c"),
    )
    assert repo.appends[0]["tool_ids"] == ("b", "a", "c")


@pytest.mark.asyncio
async def test_returns_version_no_from_repository():
    repo = FakeRepository()
    result = await _use_case(repo).append(
        session_id="s1", user_id="7", assembled="p", tool_ids=()
    )
    assert result.version_no == 2


# ── 소유권 (Design §4.5 — 404, 403 아님) ────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_or_foreign_session_raises_not_found():
    repo = FakeRepository(session_found=False)
    with pytest.raises(PromptSessionNotFoundError):
        await _use_case(repo).append(
            session_id="s1", user_id="7", assembled="p", tool_ids=()
        )


@pytest.mark.asyncio
async def test_ownership_check_precedes_append():
    """소유권 실패 시 저장 시도 자체가 없어야 한다."""
    repo = FakeRepository(session_found=False)
    with pytest.raises(PromptSessionNotFoundError):
        await _use_case(repo).append(
            session_id="s1", user_id="7", assembled="p", tool_ids=()
        )
    assert repo.appends == []


# ── 로깅 (PII 미기록) ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_does_not_contain_prompt_body():
    repo = FakeRepository()
    logger = FakeLogger()
    use_case = AppendHumanVersionUseCase(repository=repo, logger=logger)
    secret = "주민등록번호 123456-1234567 를 포함한 프롬프트"
    await use_case.append(
        session_id="s1", user_id="7", assembled=secret, tool_ids=()
    )
    dumped = repr(logger.records)
    assert secret not in dumped
    assert logger.records, "관측용 로그는 남겨야 한다"
