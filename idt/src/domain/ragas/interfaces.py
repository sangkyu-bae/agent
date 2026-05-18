"""RAGAS 평가 도메인 인터페이스."""
from abc import ABC, abstractmethod

from src.domain.ragas.entities import EvaluationResult, EvaluationRun


class EvaluationRepositoryInterface(ABC):
    """평가 결과 저장소 인터페이스."""

    @abstractmethod
    async def save_run(self, run: EvaluationRun, request_id: str) -> EvaluationRun: ...

    @abstractmethod
    async def update_run(self, run: EvaluationRun, request_id: str) -> None: ...

    @abstractmethod
    async def get_run(self, run_id: str, request_id: str) -> EvaluationRun | None: ...

    @abstractmethod
    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvaluationRun], int]: ...

    @abstractmethod
    async def delete_run(self, run_id: str, request_id: str) -> bool: ...

    @abstractmethod
    async def save_result(self, result: EvaluationResult, request_id: str) -> None: ...

    @abstractmethod
    async def save_results_bulk(
        self, results: list[EvaluationResult], request_id: str
    ) -> None: ...

    @abstractmethod
    async def get_results_by_run(
        self, run_id: str, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvaluationResult], int]: ...

    @abstractmethod
    async def get_run_summary(
        self, run_id: str, request_id: str
    ) -> dict[str, float]: ...

    @abstractmethod
    async def save_testset(self, testset: dict, request_id: str) -> None: ...

    @abstractmethod
    async def list_testsets(
        self, limit: int, offset: int, request_id: str
    ) -> tuple[list[dict], int]: ...

    @abstractmethod
    async def get_testset(self, testset_id: str, request_id: str) -> dict | None: ...

    @abstractmethod
    async def delete_testset(self, testset_id: str, request_id: str) -> bool: ...


class EvaluatorInterface(ABC):
    """평가 실행 엔진 인터페이스."""

    @abstractmethod
    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        metrics: list[str],
        request_id: str,
    ) -> dict[str, float]: ...
