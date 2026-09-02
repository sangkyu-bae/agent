"""SweepRepositoryInterface: 모델 스윕 저장소 추상화.

Design Ref: §9.1 — Infrastructure layer가 이 인터페이스를 구현한다.
구현체는 내부에서 commit()/rollback()을 호출하지 않는다 (docs/rules/db-session.md).
"""
from abc import ABC, abstractmethod

from src.domain.eval_sweep.entity import EvaluationSweep, SweepRow


class SweepRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, sweep: EvaluationSweep, request_id: str) -> EvaluationSweep:
        """신규 스윕 저장."""

    @abstractmethod
    async def update(self, sweep: EvaluationSweep, request_id: str) -> None:
        """상태·진행률·완료 시각 갱신."""

    @abstractmethod
    async def get(self, sweep_id: str, request_id: str) -> EvaluationSweep | None:
        """PK 기준 단건 조회 (소유권 판정은 UseCase 책임)."""

    @abstractmethod
    async def list_by_user(
        self,
        user_id: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvaluationSweep], int]:
        """소유자 기준 목록 + 전체 건수. user_id=None이면 전체(관리자)."""

    @abstractmethod
    async def get_rows(self, sweep_id: str, request_id: str) -> list[SweepRow]:
        """모델별 4축 집계 — evaluation_run ⋈ evaluation_result ⋈ ai_run.

        ai_run 조인에 실패한 지표는 None(N/A)으로 채운다 (Design D11).
        """

    @abstractmethod
    async def delete(self, sweep_id: str, request_id: str) -> bool:
        """스윕 삭제. 하위 evaluation_run은 FK CASCADE로 함께 삭제된다."""
