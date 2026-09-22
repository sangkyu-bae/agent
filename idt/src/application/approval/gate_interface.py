"""ApprovalGateInterface — 게이트 구현 교체 지점.

Design Ref: §2.0 (Option C 선택 근거), Plan FR-17.

지금 구현체는 StatelessGate(= ApprovalGateMiddleware + 래퍼 신호 리프트)다.
LangGraph checkpointer 를 도입하면 interrupt() 기반 InterruptGate 로 DI 만
교체하면 된다 — 위키 stateless-hitl D9 의 PlannerInterface 와 같은 손놀림.

application 레이어에 두는 이유: 파라미터가 langchain 미들웨어 인스턴스를
물기 때문이다. domain 에 두면 domain→langchain 역참조가 된다.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class ApprovalGateInterface(Protocol):
    """워커에 부착할 게이트 미들웨어를 만든다.

    구현체는 '차단 방식' 만 다르고 호출 계약은 같다:
      - StatelessGate: handler 미호출 + 마커 ToolMessage (런 정상 종료)
      - InterruptGate: interrupt() 로 그래프 일시정지 (checkpointer 필요)
    """

    def build_for_worker(self, *, tool_id: str, worker_id: str) -> object:
        """해당 워커용 게이트 미들웨어 인스턴스를 만든다.

        워커마다 새 인스턴스여야 한다 (builtin-middleware D6 — 상태 공유 금지).

        Raises:
            Exception: 조립 실패. 호출측은 이를 삼키지 않는다 — 안전 기능이
                조용히 빠지면 승인 없이 부작용이 실행된다 (fail-closed).
        """
        ...
