"""ComposeAgentUseCase 단위 테스트 — Mock 의존성, DB 무저장 검증."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_composer.composer import (
    _CapabilityOutput,
    _ComposeOutput,
    _WorkerOutput,
)
from src.application.agent_composer.compose_agent_use_case import ComposeAgentUseCase
from src.application.agent_composer.schemas import (
    ComposeAgentRequest,
    ComposeCurrentConfig,
    ComposeHistoryTurn,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _make_default_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _mcp_catalog_entry(tool_name: str, server_id: str = "srv-1") -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"cat-{tool_name}",
        tool_id=f"mcp:{server_id}:{tool_name}",
        source="mcp",
        name=tool_name,
        description=f"{tool_name} MCP 도구",
        mcp_server_id=server_id,
    )


def _mcp_registration(server_id: str = "srv-1") -> MCPServerRegistration:
    now = datetime.now(timezone.utc)
    return MCPServerRegistration(
        id=server_id,
        user_id="user-1",
        name="테스트 MCP 서버",
        description="테스트용 MCP 서버",
        endpoint="https://mcp.example.com",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_output(
    workers: list[_WorkerOutput],
    capabilities: list[_CapabilityOutput] | None = None,
    system_prompt: str = "생성된 프롬프트",
) -> _ComposeOutput:
    return _ComposeOutput(
        capabilities=capabilities
        or [
            _CapabilityOutput(
                capability="기본 역량",
                matched_tool_ids=[w.tool_id for w in workers],
                reason="커버 가능",
            )
        ],
        workers=workers,
        flow_hint="LLM이 만든 flow_hint",
        system_prompt=system_prompt,
        agent_name="제안된 이름",
        notes="",
    )


def _make_use_case(
    output: _ComposeOutput,
    catalog_entries: list[ToolCatalogEntry] | None = None,
    registrations: list[MCPServerRegistration] | None = None,
):
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=output)

    tool_catalog_repo = MagicMock()
    tool_catalog_repo.list_active = AsyncMock(return_value=catalog_entries or [])

    mcp_server_repo = MagicMock()
    mcp_server_repo.find_all_active = AsyncMock(return_value=registrations or [])

    llm_model_repository = MagicMock()
    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    logger = MagicMock()

    use_case = ComposeAgentUseCase(
        composer=composer,
        tool_catalog_repo=tool_catalog_repo,
        mcp_server_repo=mcp_server_repo,
        llm_model_repository=llm_model_repository,
        logger=logger,
    )
    return use_case, composer, tool_catalog_repo, mcp_server_repo


class TestComposeAgentUseCase:
    @pytest.mark.asyncio
    async def test_mixed_internal_and_mcp_draft(self):
        """① 내부+MCP 혼합 초안: mcp:{srv}:{tool}이 mcp_{srv}로 매핑된다."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="search_worker",
                          description="검색", sort_order=0),
            _WorkerOutput(tool_id="mcp:srv-1:fetch_page", worker_id="fetch_worker",
                          description="페이지 수집", sort_order=1),
        ])
        use_case, _, _, _ = _make_use_case(
            output, catalog_entries=[_mcp_catalog_entry("fetch_page")]
        )
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색해서 수집하는 에이전트"), "req-1"
        )
        assert result.coverage == "full"
        assert result.tool_ids == ["tavily_search", "mcp_srv-1"]
        assert result.llm_model_id == "model-default"
        assert result.system_prompt == "생성된 프롬프트"

    @pytest.mark.asyncio
    async def test_same_server_tools_merged_into_one_worker(self):
        """② 같은 서버의 개별 도구 2건 → mcp_{srv} 워커 1개로 병합."""
        output = _make_output([
            _WorkerOutput(tool_id="mcp:srv-1:fetch_page", worker_id="fetch_worker",
                          description="페이지 수집", sort_order=0),
            _WorkerOutput(tool_id="mcp:srv-1:parse_html", worker_id="parse_worker",
                          description="HTML 파싱", sort_order=1),
        ])
        use_case, _, _, _ = _make_use_case(
            output,
            catalog_entries=[
                _mcp_catalog_entry("fetch_page"),
                _mcp_catalog_entry("parse_html"),
            ],
        )
        result = await use_case.execute(
            ComposeAgentRequest(user_request="웹 수집 에이전트"), "req-1"
        )
        assert result.tool_ids == ["mcp_srv-1"]
        assert len(result.workers) == 1
        assert "페이지 수집" in result.workers[0].description
        assert "HTML 파싱" in result.workers[0].description

    @pytest.mark.asyncio
    async def test_worker_instruction_exposed_in_response(self):
        """compose-tool-instructions FR-03: workers[].instruction 응답 노출."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="search_worker",
                          description="검색", sort_order=0,
                          instruction="최신 정보 질문에만 사용."),
        ])
        use_case, _, _, _ = _make_use_case(output)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색 에이전트"), "req-1"
        )
        assert result.workers[0].instruction == "최신 정보 질문에만 사용."

    @pytest.mark.asyncio
    async def test_merged_workers_merge_instructions(self):
        """compose-tool-instructions FR-04: 병합 시 instruction '; ' 연결."""
        output = _make_output([
            _WorkerOutput(tool_id="mcp:srv-1:fetch_page", worker_id="fetch_worker",
                          description="페이지 수집", sort_order=0,
                          instruction="URL을 받아 본문을 수집."),
            _WorkerOutput(tool_id="mcp:srv-1:parse_html", worker_id="parse_worker",
                          description="HTML 파싱", sort_order=1,
                          instruction="수집된 HTML에서 표를 추출."),
        ])
        use_case, _, _, _ = _make_use_case(
            output,
            catalog_entries=[
                _mcp_catalog_entry("fetch_page"),
                _mcp_catalog_entry("parse_html"),
            ],
        )
        result = await use_case.execute(
            ComposeAgentRequest(user_request="수집 에이전트"), "req-1"
        )
        assert len(result.workers) == 1
        assert "URL을 받아 본문을 수집." in result.workers[0].instruction
        assert "수집된 HTML에서 표를 추출." in result.workers[0].instruction

    @pytest.mark.asyncio
    async def test_catalog_empty_falls_back_to_server_meta(self):
        """③ 카탈로그 MCP 0건 → 서버 단위 메타 폴백(D2) + notes 안내."""
        output = _make_output([
            _WorkerOutput(tool_id="mcp_srv-1", worker_id="mcp_srv-1_worker",
                          description="MCP 서버 도구", sort_order=0),
        ])
        use_case, composer, _, mcp_repo = _make_use_case(
            output, catalog_entries=[], registrations=[_mcp_registration()]
        )
        result = await use_case.execute(
            ComposeAgentRequest(user_request="MCP 작업 에이전트"), "req-1"
        )
        mcp_repo.find_all_active.assert_awaited_once()
        candidates = composer.compose.call_args[0][1]
        assert any(c.tool_id == "mcp_srv-1" and c.server_level for c in candidates)
        assert result.tool_ids == ["mcp_srv-1"]
        assert "동기화" in result.notes

    @pytest.mark.asyncio
    async def test_hallucinated_tool_id_dropped_with_notes(self):
        """④ 후보에 없는 tool_id는 drop되고 notes에 기록된다."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="search_worker",
                          description="검색", sort_order=0),
            _WorkerOutput(tool_id="imaginary_tool", worker_id="fake_worker",
                          description="상상 도구", sort_order=1),
        ])
        use_case, _, _, _ = _make_use_case(output)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색 에이전트"), "req-1"
        )
        assert result.tool_ids == ["tavily_search"]
        assert "imaginary_tool" in result.notes

    @pytest.mark.asyncio
    async def test_coverage_none_returns_empty_draft(self):
        """⑤ 워커 0개면 coverage=none + 초안 필드 빈 값."""
        output = _make_output(
            workers=[],
            capabilities=[
                _CapabilityOutput(
                    capability="사내 ERP 조회",
                    matched_tool_ids=[],
                    reason="매칭 도구 없음",
                    suggestion="ERP MCP 등록 필요",
                )
            ],
        )
        use_case, _, _, _ = _make_use_case(output)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="ERP 조회 에이전트"), "req-1"
        )
        assert result.coverage == "none"
        assert result.tool_ids == []
        assert result.workers == []
        assert result.system_prompt == ""
        assert result.flow_hint == ""
        assert result.missing_capabilities[0].capability == "사내 ERP 조회"

    @pytest.mark.asyncio
    async def test_unknown_llm_model_id_raises(self):
        """⑥ llm_model_id 미존재 → ValueError."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="w",
                          description="검색", sort_order=0),
        ])
        use_case, _, _, _ = _make_use_case(output)
        use_case._llm_model_repository.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="LLM 모델"):
            await use_case.execute(
                ComposeAgentRequest(user_request="검색", llm_model_id="ghost"),
                "req-1",
            )

    @pytest.mark.asyncio
    async def test_no_db_write(self):
        """⑦ compose는 어떤 저장도 호출하지 않는다."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="w",
                          description="검색", sort_order=0),
        ])
        use_case, _, catalog_repo, mcp_repo = _make_use_case(output)
        await use_case.execute(ComposeAgentRequest(user_request="검색"), "req-1")
        catalog_repo.save.assert_not_called()
        catalog_repo.upsert_by_tool_id.assert_not_called()
        mcp_repo.save.assert_not_called()
        mcp_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_supplied_name_echoed(self):
        """요청 name이 있으면 LLM 제안 대신 그대로 반환."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="w",
                          description="검색", sort_order=0),
        ])
        use_case, _, _, _ = _make_use_case(output)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색", name="내가 정한 이름"), "req-1"
        )
        assert result.name_suggestion == "내가 정한 이름"

    @pytest.mark.asyncio
    async def test_current_config_and_history_passed_to_composer(self):
        """B6: current_config는 그대로, history는 절단(dict 변환)되어 composer에 전달."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="w",
                          description="검색", sort_order=0),
        ])
        use_case, composer, _, _ = _make_use_case(output)
        current = ComposeCurrentConfig(
            name="재무 리포터", tool_ids=["excel_export"], temperature=0.7
        )
        history = [
            ComposeHistoryTurn(role="user", content=f"메시지{i}") for i in range(8)
        ]
        await use_case.execute(
            ComposeAgentRequest(
                user_request="tavily 도구 추가해줘",
                current_config=current,
                history=history,
            ),
            "req-1",
        )
        kwargs = composer.compose.call_args.kwargs
        assert kwargs["current_config"] is current
        assert len(kwargs["history"]) == 6  # 최근 6턴 절단
        assert kwargs["history"][0] == {"role": "user", "content": "메시지2"}

    @pytest.mark.asyncio
    async def test_without_new_fields_composer_receives_none(self):
        """B6 하위호환: 신규 필드 미전송 시 composer에 None 전달."""
        output = _make_output([
            _WorkerOutput(tool_id="tavily_search", worker_id="w",
                          description="검색", sort_order=0),
        ])
        use_case, composer, _, _ = _make_use_case(output)
        await use_case.execute(ComposeAgentRequest(user_request="검색"), "req-1")
        kwargs = composer.compose.call_args.kwargs
        assert kwargs["current_config"] is None
        assert kwargs["history"] is None

    @pytest.mark.asyncio
    async def test_tool_count_clamped_with_notes(self):
        """D7: MAX_TOOLS(5) 초과 시 sort_order 상위 5개만 유지 + notes.

        서로 다른 MCP 서버 6개의 도구를 선택하게 하여 병합 없이 워커 6개를 만든다.
        """
        mcp_catalog = [
            ToolCatalogEntry(
                id=f"cat-{i}", tool_id=f"mcp:s{i}:tool_{i}", source="mcp",
                name=f"도구{i}", description=f"도구{i} 설명", mcp_server_id=f"s{i}",
            )
            for i in range(6)
        ]
        mcp_workers = [
            _WorkerOutput(tool_id=f"mcp:s{i}:tool_{i}", worker_id=f"w{i}",
                          description=f"도구{i}", sort_order=i)
            for i in range(6)
        ]
        output = _make_output(mcp_workers)
        use_case, _, _, _ = _make_use_case(output, catalog_entries=mcp_catalog)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="여러 도구 에이전트"), "req-1"
        )
        assert len(result.workers) == 5
        assert "mcp_s5" in result.notes
