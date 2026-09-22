"""CreateAgentUseCase degraded 게이트 — prompt-fallback-visibility module-1 (T-06~T-10).

Design §4-2 — Step 3(system_prompt 필수) 직후, Step 4(저장) 직전에
`prompt_version_id` 로 버전을 **DB 에서 재조회**해 판정한다.
클라이언트가 보내는 degraded 플래그는 믿지 않는다 (Option C / D2).

게이트는 **전부 선택적**이다:
  · Port 미주입 → 게이트 비활성 (파이프라인 `_run_create`·기존 테스트 무변경)
  · `prompt_version_id` 미전달 → 통과 (수동 생성·Fix 경로·API 직접)
  · 조회 실패 → 통과 + warning (관측성 결함이 생성 실패로 번지지 않게)
"""
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest

from tests.application.agent_builder.test_create_agent_use_case import (
    PROMPT,
    _make_default_llm_model,
)

_DEGRADED = PROMPT  # 게이트 대상이 되는 "저장된 원본"


@dataclass
class _Version:
    """`prompt_version` 행의 판정에 필요한 필드만."""

    degraded: bool
    assembled: str
    reason: str | None = None


class FakePromptVersionReader:
    """`PromptRepositoryPort.find_version` 대역."""

    def __init__(self, version: _Version | None = None,
                 raises: Exception | None = None) -> None:
        self._version = version
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def find_version(self, version_id: str, user_id: str) -> Any:
        self.calls.append((version_id, user_id))
        if self._raises is not None:
            raise self._raises
        return self._version


def _use_case(reader: FakePromptVersionReader | None):
    repository = MagicMock()
    llm_repo = MagicMock()
    model = _make_default_llm_model()
    llm_repo.find_by_id = AsyncMock(return_value=model)
    llm_repo.find_default = AsyncMock(return_value=model)

    async def _save(agent, req_id):
        return agent

    repository.save = AsyncMock(side_effect=_save)
    logger = MagicMock()
    uc = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_repo,
        perm_repo=MagicMock(),
        logger=logger,
        prompt_version_reader=reader,
    )
    return uc, repository, logger


def _request(system_prompt: str = _DEGRADED,
             prompt_version_id: str | None = "pv-1") -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="엑셀 변환 에이전트",
        name="엑셀 변환기",
        user_id="user-1",
        system_prompt=system_prompt,
        prompt_version_id=prompt_version_id,
    )


class TestGateInactive:
    """T-06 / T-07 — 게이트가 꺼지는 조건은 전부 '통과'다."""

    async def test_no_reader_injected_skips_gate(self) -> None:
        """T-06 — Port 미주입이면 게이트 자체가 없다 (기존 호출부 무변경)."""
        uc, repository, _ = _use_case(reader=None)
        result = await uc.execute(_request(), "req-1")
        assert result.agent_id
        repository.save.assert_awaited_once()

    async def test_no_version_id_skips_lookup(self) -> None:
        """T-07 — 버전 id 가 없으면 조회조차 하지 않는다 (FR-06)."""
        reader = FakePromptVersionReader(_Version(True, _DEGRADED))
        uc, repository, _ = _use_case(reader)

        await uc.execute(_request(prompt_version_id=None), "req-1")

        assert reader.calls == []
        repository.save.assert_awaited_once()


class TestLookupFailure:
    """T-08 — 조회 실패는 생성 실패로 번지지 않는다."""

    async def test_lookup_exception_allows_and_warns(self) -> None:
        reader = FakePromptVersionReader(raises=RuntimeError("db down"))
        uc, repository, logger = _use_case(reader)

        result = await uc.execute(_request(), "req-1")

        assert result.agent_id
        repository.save.assert_awaited_once()
        logger.warning.assert_called()

    async def test_version_not_found_allows(self) -> None:
        """없거나 타인 소유 → 검증 근거가 없으므로 통과 (FR-02)."""
        reader = FakePromptVersionReader(version=None)
        uc, repository, _ = _use_case(reader)

        await uc.execute(_request(), "req-1")

        repository.save.assert_awaited_once()

    async def test_lookup_scoped_to_requester(self) -> None:
        """조회는 요청자 소유로 한정한다."""
        reader = FakePromptVersionReader(_Version(False, _DEGRADED))
        uc, _, _ = _use_case(reader)

        await uc.execute(_request(), "req-1")

        assert reader.calls == [("pv-1", "user-1")]


class TestBlocksUneditedDegraded:
    """T-09 — degraded 버전을 편집 없이 저장하면 거부한다 (Plan SC-02)."""

    async def test_raises_value_error(self) -> None:
        reader = FakePromptVersionReader(_Version(True, _DEGRADED, "timeout"))
        uc, repository, _ = _use_case(reader)

        with pytest.raises(ValueError):
            await uc.execute(_request(system_prompt=_DEGRADED), "req-1")

        repository.save.assert_not_awaited()

    async def test_error_carries_reason(self) -> None:
        """FR-07 — 422 본문에 사유가 실려야 프론트가 안내할 수 있다."""
        reader = FakePromptVersionReader(_Version(True, _DEGRADED, "timeout"))
        uc, _, _ = _use_case(reader)

        with pytest.raises(ValueError) as exc:
            await uc.execute(_request(system_prompt=_DEGRADED), "req-1")

        assert "timeout" in str(exc.value)

    async def test_allows_when_edited(self) -> None:
        """Plan SC-03 / FR-05 — 편집했으면 저장된다."""
        reader = FakePromptVersionReader(_Version(True, _DEGRADED, "timeout"))
        uc, repository, _ = _use_case(reader)

        await uc.execute(
            _request(system_prompt=_DEGRADED + "\n- 내가 추가한 규칙"), "req-1"
        )

        repository.save.assert_awaited_once()

    async def test_allows_healthy_version(self) -> None:
        """degraded 가 아니면 편집 여부와 무관하게 통과."""
        reader = FakePromptVersionReader(_Version(False, _DEGRADED))
        uc, repository, _ = _use_case(reader)

        await uc.execute(_request(system_prompt=_DEGRADED), "req-1")

        repository.save.assert_awaited_once()


class TestToolsDegradedNotBlocked:
    """T-10 — `tools` 단계 degraded 는 저장을 막지 않는다 (D5, Plan SC-07).

    게이트는 **프롬프트 버전**의 degraded 만 본다. 도구 추천 실패는
    `prompt_version` 에 기록되지 않으므로 구조적으로 게이트 대상이 아니다
    — "쓸 수 있는 결과"(사용자가 지정한 도구)가 존재하기 때문이다.
    """

    async def test_healthy_prompt_with_user_tools_saves(self) -> None:
        reader = FakePromptVersionReader(_Version(False, _DEGRADED))
        uc, repository, _ = _use_case(reader)
        req = _request()
        req.tool_ids = ["internal:excel_export"]

        await uc.execute(req, "req-1")

        repository.save.assert_awaited_once()


class TestHttpStatusContract:
    """FR-07 — 라우터가 게이트 거부를 **422** 로 내보낸다.

    `POST /api/v1/agents` 의 ValueError 는 `_attach_skill_http_error` 를 거치는데,
    이 헬퍼는 **메시지 부분문자열**로 상태코드를 고른다
    ("찾을 수 없"→404, "이미 부착"/"최대"→409, 그 외→422).
    게이트 문구를 누가 "최대 N회…"처럼 바꾸면 조용히 409 가 된다 — 그래서
    실제 게이트가 던진 메시지 그대로 매핑 결과를 고정한다.
    """

    async def test_gate_rejection_maps_to_422(self) -> None:
        from src.api.routes.agent_builder_router import _attach_skill_http_error

        reader = FakePromptVersionReader(_Version(True, _DEGRADED, "timeout"))
        uc, _, _ = _use_case(reader)

        with pytest.raises(ValueError) as exc:
            await uc.execute(_request(system_prompt=_DEGRADED), "req-1")

        assert _attach_skill_http_error(exc.value).status_code == 422
