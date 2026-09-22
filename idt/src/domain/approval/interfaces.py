"""approval-gate 도메인 인터페이스 (포트).

Design Ref: §2.3, §9.3. 구현체는 infrastructure/approval 에 둔다.

DB-001: Repository 는 내부에서 commit()/rollback() 을 호출하지 않는다 —
트랜잭션 경계는 호출측 UseCase 가 소유한다. `claim_due` 도 flush 까지만 한다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.domain.approval.entity import ApprovalRequest, ApprovalStatus


@dataclass(frozen=True)
class ExecutionResult:
    """집행기 산출물 — 재개 시 워커 결과로 주입된다.

    실패를 예외가 아닌 값으로 돌려주는 이유: 집행 실패는 정상 흐름의 한
    갈래(failed 상태 + 사람 재판단)이지 시스템 오류가 아니다 (FR-25).
    """

    ok: bool
    output: str
    error_message: str | None = None


class ApprovalRepositoryInterface(ABC):
    @abstractmethod
    async def create(self, request: ApprovalRequest, request_id: str) -> None:
        """승인 요청 적재.

        idempotency_key 중복은 UNIQUE 제약 위반으로 올라온다 — 같은 도구
        호출로 pending 이 두 번 생기지 않는다 (이중 집행 1차 저지선).
        """

    @abstractmethod
    async def find(self, approval_id: str, request_id: str) -> ApprovalRequest | None:
        ...

    @abstractmethod
    async def find_active_by_run(
        self, run_id: str, request_id: str
    ) -> ApprovalRequest | None:
        """런당 활성 pending 1건 불변식(FR-06) 확인용."""

    @abstractmethod
    async def list_for_user(
        self,
        agent_ids: tuple[str, ...],
        request_id: str,
        *,
        statuses: tuple[ApprovalStatus, ...],
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ApprovalRequest], int]:
        """소유 에이전트 범위의 목록 + 총계.

        user_id 가 아니라 agent_ids 를 받는 이유: 리포지토리가 다른
        애그리게이트(agent_definition)의 ORM 모델을 참조하면 공유
        Base.metadata 가 오염된다. 소유 해석은 UseCase 의 몫이고, 권한
        판정은 ApprovalPolicy.can_decide 가 별도로 한다.
        """

    @abstractmethod
    async def count_unseen(
        self, agent_ids: tuple[str, ...], request_id: str
    ) -> int:
        """벨 배지용 미확인 건수 (seen_at IS NULL)."""

    @abstractmethod
    async def compare_and_set_status(
        self,
        approval_id: str,
        *,
        expected: ApprovalStatus,
        new_status: ApprovalStatus,
        request_id: str,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
        decision_reason: str | None = None,
        execute_after: datetime | None = None,
        executed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        """조건부 UPDATE — 영향 행 0 이면 False.

        이중 집행 방어 2차 저지선. 승인 버튼 2회 클릭 시 두 번째는 expected
        불일치로 False 가 되어 집행이 한 번만 일어난다. 애플리케이션 레벨
        read-then-write 대신 DB 원자성에 기대는 이유다.
        """

    @abstractmethod
    async def claim_due(
        self, now_utc: datetime, request_id: str, *, limit: int = 50
    ) -> list[ApprovalRequest]:
        """집행 시각이 도래한 scheduled 건 선점.

        agent_schedule.claim_due 와 동일하게 FOR UPDATE SKIP LOCKED 로 잠긴
        행을 건너뛴다 — 다중 tick 워커가 같은 건을 집행하지 않는다
        (이중 집행 3차 저지선). commit 은 호출측 트랜잭션 블록이 담당한다.
        """

    @abstractmethod
    async def mark_seen(
        self, approval_id: str, agent_ids: tuple[str, ...], request_id: str
    ) -> None:
        """소유 에이전트 범위의 건만 확인 처리 (Check G7 — user_id 무시 결함 수정)."""

    @abstractmethod
    async def expire_overdue(self, now_utc: datetime, request_id: str) -> int:
        """만료 경과 건을 expired 로 일괄 전이하고 건수를 돌려준다."""


class ActionExecutorInterface(ABC):
    """승인된 도구 호출의 실제 집행기.

    새 부작용 도구는 이 포트만 구현하면 게이트·승인·재개는 손대지 않는다.
    구현체는 CompositeActionExecutor 가 `supports()` 로 고른다 — 받을 구현체가
    없는 도구는 집행 실패로 끝난다 (approval-gate-phase2 Plan SC-2).
    """

    @abstractmethod
    async def execute(
        self,
        *,
        tool_id: str,
        tool_args: dict,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> ExecutionResult:
        """집행. 예외를 던지지 않고 ExecutionResult 로 성패를 돌려준다.

        idempotency_key (approval-gate-phase2 D-05): 승인 요청의 멱등키.
        대상 시스템이 받을 수 있을 때만 전달해 재승인 시 이중 집행을 막는다.
        선택 인자라 기존 호출부·구현체는 그대로 동작한다.
        """

    @abstractmethod
    def supports(self, tool_id: str) -> bool:
        """이 집행기가 처리할 수 있는 도구인지. 디스패치 판정용."""
