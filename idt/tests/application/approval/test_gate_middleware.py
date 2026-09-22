"""ApprovalGateMiddleware 단위 테스트.

Design Ref: §2.1 ① — 미들웨어는 순수하다. DB·그래프 상태를 만지지 않고
실도구 handler 를 호출하지 않으며 마커 ToolMessage 만 돌려준다.
그 덕에 이 파일 전체가 DB·langgraph 없이 돌아간다.
"""
import pytest
from langchain_core.messages import ToolMessage

from src.application.approval.gate_middleware import ApprovalGateMiddleware
from src.domain.approval.policies import ApprovalSignalPolicy


class _Req:
    """ToolCallRequest 최소 대역 (tool_call/tool/state/runtime)."""

    def __init__(self, name="email_send", args=None, call_id="tc1"):
        self.tool_call = {"name": name, "args": args or {"to": "a@b.c"}, "id": call_id}
        self.tool = None
        self.state = {}
        self.runtime = None


def _gate(**over) -> ApprovalGateMiddleware:
    kwargs = {"tool_id": "email_send", "worker_id": "w1"}
    kwargs.update(over)
    return ApprovalGateMiddleware(**kwargs)


def _boom(_req):
    """호출되면 안 되는 handler — 실도구 실행을 흉내낸다."""
    raise AssertionError("실도구 handler 가 호출되었다 — 게이트가 뚫렸다")


class TestBlocking:
    def test_실도구_handler를_호출하지_않는다(self):
        """게이트의 존재 이유 — 여기서 실패하면 승인 없이 이메일이 나간다."""
        result = _gate().wrap_tool_call(_Req(), _boom)
        assert isinstance(result, ToolMessage)

    @pytest.mark.asyncio
    async def test_async_경로도_handler를_호출하지_않는다(self):
        """워커는 ainvoke 로 돌므로 async 경로가 실제 경로다."""

        async def aboom(_req):
            raise AssertionError("실도구 handler 가 호출되었다")

        result = await _gate().awrap_tool_call(_Req(), aboom)
        assert isinstance(result, ToolMessage)

    def test_반환_ToolMessage가_원래_tool_call_id를_유지한다(self):
        """id 가 어긋나면 OpenAI 가 고아 tool 메시지로 400 을 낸다."""
        result = _gate().wrap_tool_call(_Req(call_id="tc-42"), _boom)
        assert result.tool_call_id == "tc-42"


class TestMarker:
    def test_마커를_다시_파싱할_수_있다(self):
        result = _gate().wrap_tool_call(_Req(), _boom)
        signal = ApprovalSignalPolicy.extract([result])
        assert signal is not None
        assert signal.tool_id == "email_send"
        assert signal.tool_args == {"to": "a@b.c"}
        assert signal.tool_call_id == "tc1"

    def test_생성자의_tool_id를_싣는다(self):
        """request.tool_call["name"] 은 MCP 에서 UUID 접두 합성명이라
        신뢰할 수 없다 (위키 mcp-runtime-tool-shape). 컴파일러가 아는
        저장 형식 tool_id 를 생성자로 받아 그대로 싣는다."""
        result = _gate(tool_id="mcp:rate_update").wrap_tool_call(
            _Req(name="a1b2c3d4_rate_update"), _boom
        )
        signal = ApprovalSignalPolicy.extract([result])
        assert signal.tool_id == "mcp:rate_update"

    def test_한글_인자가_보존된다(self):
        req = _Req(args={"본문": "기준금리를 3.25%로 변경합니다"})
        signal = ApprovalSignalPolicy.extract(
            [_gate().wrap_tool_call(req, _boom)]
        )
        assert signal.tool_args["본문"] == "기준금리를 3.25%로 변경합니다"

    def test_초안이_인자에서_추출된다(self):
        """사람이 검토할 본문 — draft 키가 있으면 그것을 초안으로 쓴다."""
        req = _Req(args={"draft": "메일 본문입니다", "to": "a@b.c"})
        signal = ApprovalSignalPolicy.extract(
            [_gate().wrap_tool_call(req, _boom)]
        )
        assert signal.draft == "메일 본문입니다"

    def test_draft_키가_없으면_인자_전체를_초안으로_보여준다(self):
        """사람이 무엇을 승인하는지 화면에서 볼 수 있어야 한다."""
        signal = ApprovalSignalPolicy.extract(
            [_gate().wrap_tool_call(_Req(args={"to": "a@b.c"}), _boom)]
        )
        assert "a@b.c" in signal.draft

    def test_안내_문구가_포함된다(self):
        """워커 LLM 이 '보냈다' 가 아니라 '승인 대기' 로 답하게 하는 신호."""
        result = _gate().wrap_tool_call(_Req(), _boom)
        assert "승인" in result.content


class TestPurity:
    def test_생성자가_DB나_상태를_받지_않는다(self):
        """Option C 의 핵심 — repo 를 받으면 Builder 에 DI 가 필요해진다."""
        import inspect

        params = set(inspect.signature(ApprovalGateMiddleware.__init__).parameters)
        assert params == {"self", "tool_id", "worker_id"}

    def test_동일_입력에_동일_출력(self):
        a = _gate().wrap_tool_call(_Req(), _boom).content
        b = _gate().wrap_tool_call(_Req(), _boom).content
        assert a == b

    def test_인스턴스가_상태를_남기지_않는다(self):
        """워커마다 새 인스턴스(D6)지만, 한 인스턴스가 여러 번 불려도 안전해야."""
        gate = _gate()
        first = gate.wrap_tool_call(_Req(call_id="t1"), _boom)
        second = gate.wrap_tool_call(_Req(call_id="t2"), _boom)
        assert first.tool_call_id == "t1"
        assert second.tool_call_id == "t2"


class TestStatelessGate:
    """Check G9 — Protocol 에 실제 구현체가 있어야 B 전환 지점이 성립한다."""

    def test_Protocol을_만족한다(self):
        from src.application.approval.gate_interface import ApprovalGateInterface
        from src.application.approval.gate_middleware import StatelessGate

        assert isinstance(StatelessGate(), ApprovalGateInterface)

    def test_워커마다_새_미들웨어를_만든다(self):
        from src.application.approval.gate_middleware import StatelessGate

        gate = StatelessGate()
        a = gate.build_for_worker(tool_id="t", worker_id="w")
        b = gate.build_for_worker(tool_id="t", worker_id="w")
        assert isinstance(a, ApprovalGateMiddleware) and a is not b

    def test_컴파일러가_Protocol을_경유한다(self):
        """게이트 구현을 바꾸면 컴파일러가 그것을 쓴다 — 교체 지점 실증."""
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler
        from src.domain.approval.entity import GateSettings

        built = []

        class _FakeGate:
            def build_for_worker(self, *, tool_id, worker_id):
                built.append((tool_id, worker_id))
                return "fake-mw"

        compiler = WorkflowCompiler.__new__(WorkflowCompiler)
        compiler._logger = __import__("unittest.mock").mock.MagicMock()
        compiler.approval_gate = _FakeGate()
        worker_def = type("W", (), {"tool_id": "email_send", "worker_id": "w1"})()
        gate = GateSettings(mode="always", execute_after=None,
                            expires_hours=168, is_enforced=False)
        result = compiler._approval_gate_middleware(
            worker_def=worker_def, gate_settings=gate,
            gated_tool_ids={"email_send"},
        )
        assert result == ["fake-mw"]
        assert built == [("email_send", "w1")]
