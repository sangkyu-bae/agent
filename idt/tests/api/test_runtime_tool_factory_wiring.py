"""런타임 ToolFactory MCP DI 배선 계약 테스트 (I1-I3).

Design Ref: fix-mcp-tool-call-not-reaching-server §8.3

에이전트 실행에 쓰이는 ToolFactory에 mcp_tool_loader / mcp_repository가
주입돼 있지 않으면, MCP 워커를 가진 에이전트는 compile 단계에서 ValueError로
통째로 실패한다 — MCP 서버에는 요청이 한 번도 나가지 않는다.

이 배선은 본 기능의 Plan 수립 중 실제로 작업트리에서 사라진 적이 있다.
그때는 이를 잡는 테스트가 없었다. 이 파일이 그 그물이다.

외부 서비스(Qdrant/MySQL)가 필요하므로 연결 실패 시 skip한다 — CI가 이유 없이
빨간색이 되지 않게 하되, 환경이 갖춰지면 반드시 검증된다.
"""
import inspect

import pytest


@pytest.fixture(scope="module")
def workflow_compiler():
    """실 DI 팩토리에서 에이전트 실행용 WorkflowCompiler를 꺼낸다."""
    try:
        from src.api.main import create_agent_builder_factories

        factories = create_agent_builder_factories()
    except Exception as e:  # 외부 서비스 미기동 등
        pytest.skip(f"DI 팩토리 생성 불가 (외부 서비스 미기동?): {e}")

    build_run_agent_uc = factories[-1]
    nonlocals = inspect.getclosurevars(build_run_agent_uc).nonlocals
    compiler = nonlocals.get("workflow_compiler")
    if compiler is None:
        pytest.fail(
            "create_agent_builder_factories의 클로저에서 workflow_compiler를 "
            "찾지 못했다 — DI 구조가 바뀌었다면 이 테스트를 함께 갱신할 것"
        )
    return compiler


@pytest.fixture(scope="module")
def runtime_tool_factory(workflow_compiler):
    return workflow_compiler._tool_factory


class TestRuntimeToolFactoryMcpWiring:

    def test_mcp_tool_loader_is_injected(self, runtime_tool_factory):
        """I1a: loader 미주입이면 MCP 워커 compile이 ValueError로 죽는다."""
        assert runtime_tool_factory._mcp_tool_loader is not None, (
            "런타임 ToolFactory에 mcp_tool_loader가 없다 — MCP 워커를 가진 "
            "에이전트가 전부 실행 불가 상태다 (api/main.py의 ToolFactory(...) 확인)"
        )

    def test_mcp_repository_is_injected(self, runtime_tool_factory):
        """I1b: 컴파일러는 create_all_async에 repository를 넘기지 않는다.

        따라서 생성자 주입 repository가 없으면 폴백할 곳이 없다.
        """
        assert runtime_tool_factory._mcp_repository is not None, (
            "런타임 ToolFactory에 mcp_repository가 없다 — 컴파일러는 호출 시 "
            "repository를 넘기지 않으므로 폴백 대상이 사라진다"
        )

    def test_mcp_repository_is_session_scoped(self, runtime_tool_factory):
        """I2: 앱 싱글톤이 per-request 세션을 들면 안 된다 (DB-001).

        매 호출마다 세션을 여는 세션 스코프 어댑터여야 한다.
        """
        from src.infrastructure.mcp_registry.session_scoped_repository import (
            SessionScopedMcpServerRepository,
        )

        assert isinstance(
            runtime_tool_factory._mcp_repository, SessionScopedMcpServerRepository
        ), (
            "mcp_repository가 세션 스코프 어댑터가 아니다 — 앱 싱글톤이 "
            "AsyncSession을 붙들면 요청 간 세션이 공유된다"
        )

    def test_factory_exposes_create_all_async(self, runtime_tool_factory):
        """I3: 워커에 서버 도구 전체를 바인딩하는 진입점이 존재한다."""
        assert hasattr(runtime_tool_factory, "create_all_async")
        assert inspect.iscoroutinefunction(runtime_tool_factory.create_all_async)


class TestMiddlewareAgentToolFactoryMcpWiring:
    """I3: 미들웨어 에이전트 경로도 같은 MCP 배선 계약을 지킨다.

    Plan §6.2에서 "Needs verification"으로 남겨둔 소비자 —
    RunMiddlewareAgentUseCase는 create_async를 저장소 없이 호출하므로
    (run_middleware_agent_use_case.py) 생성자 주입 저장소가 유일한 폴백이다.

    실제 MCP 서버로 나가지 않도록 객체 속성만 검사한다.
    """

    @pytest.fixture(scope="class")
    def middleware_tool_factory(self):
        try:
            from src.api.main import create_middleware_agent_factories

            factories = create_middleware_agent_factories()
        except Exception as e:
            pytest.skip(f"DI 팩토리 생성 불가 (외부 서비스 미기동?): {e}")

        for factory in factories:
            nonlocals = inspect.getclosurevars(factory).nonlocals
            if "tool_factory" in nonlocals:
                return nonlocals["tool_factory"]
        pytest.fail("미들웨어 팩토리 클로저에서 tool_factory를 찾지 못했다")

    def test_mcp_tool_loader_is_injected(self, middleware_tool_factory):
        assert middleware_tool_factory._mcp_tool_loader is not None

    def test_mcp_repository_is_injected(self, middleware_tool_factory):
        """create_async를 저장소 없이 호출하므로 생성자 주입이 유일한 폴백이다."""
        assert middleware_tool_factory._mcp_repository is not None
