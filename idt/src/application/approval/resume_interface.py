"""RunResumerInterface — 승인 결과를 받아 멈춘 런을 이어 돌리는 포트.

Design Ref: §2.1 (재개), §7.3 (v0.2 위치 정제).

Design v0.1 은 `application/approval/resume_use_case.py` 가 WorkflowCompiler 를
직접 부르도록 적었으나, compile 호출은 인자 15개(llm_model·temperature·
tracker·callback·run_id·auth_ctx·supervisor_config·visited·skill 주입 …)이고
그 지식은 RunAgentUseCase 만 온전히 갖는다. 복제하면 관측성·스킬 주입·모델
오버라이드가 **재개 런에서만 조용히 빠진다**.

그래서 실행은 RunAgentUseCase 에 두고, approval 은 이 좁은 Protocol 로만
의존한다. 레이어는 application→application 으로 그대로다.
"""
from typing import Protocol, runtime_checkable

from src.domain.approval.entity import ApprovalRequest


@runtime_checkable
class RunResumerInterface(Protocol):
    async def resume_from_snapshot(
        self,
        approval: ApprovalRequest,
        *,
        outcome: str,
        request_id: str,
    ) -> str:
        """스냅샷을 복원해 supervisor 부터 그래프를 이어 돌린다.

        Args:
            approval: 스냅샷·워커·에이전트 정보를 담은 승인 요청
            outcome: 워커 산출물로 주입할 문장. 집행 결과 또는 거절 사유다.
                승인·거절이 같은 메커니즘을 쓰는 이유는 supervisor 입장에서
                둘 다 "워커가 이런 결과를 냈다" 로 동일하기 때문이다.
            request_id: 추적 ID

        Returns:
            재개 후 최종 답변 문자열. 재개할 수 없으면 빈 문자열.
        """
        ...
