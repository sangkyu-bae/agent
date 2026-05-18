"""Supervisor 루프 확장을 위한 Hook 프로토콜."""
from typing import Protocol

from src.application.agent_builder.supervisor_state import SupervisorState


class SupervisorHooks(Protocol):
    def force_worker(self, state: SupervisorState) -> str | None: ...
    def skip_workers(self, state: SupervisorState) -> list[str]: ...


class DefaultHooks:
    def force_worker(self, state: SupervisorState) -> str | None:
        return None

    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []
