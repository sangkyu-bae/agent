"""승인 집행 설정 (환경변수 기반).

Design Ref: approval-gate-phase2-mcp-executor §10.3.

재시도 횟수는 여기 없다 — 집행 경로의 재시도는 0 으로 코드에 고정한다
(D-10). 비가역 작업에서 켜면 안 되는 값을 설정으로 열어두지 않는다.
"""
from pydantic import Field
from pydantic_settings import BaseSettings

from src.domain.mcp.value_objects import MCPTimeoutConfig


class ApprovalExecutionConfig(BaseSettings):
    """승인된 도구 집행의 타임아웃·출력 상한."""

    APPROVAL_EXEC_CONNECT_TIMEOUT: float = Field(default=15.0, gt=0)
    # 집행은 승인 트랜잭션·claim_due 행 잠금 안에서 돈다 (Design §6.3).
    # 이 값이 곧 잠금 유지 시간의 상한이라 짧게 둔다.
    APPROVAL_EXEC_TOTAL_TIMEOUT: float = Field(default=60.0, gt=0)
    APPROVAL_EXEC_OUTPUT_MAX_CHARS: int = Field(default=8000, gt=0)

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_timeout(self) -> MCPTimeoutConfig:
        """MCP 호출 코어용 세분화 타임아웃. read 는 total 에 맞춘다."""
        return MCPTimeoutConfig(
            connect=self.APPROVAL_EXEC_CONNECT_TIMEOUT,
            read=self.APPROVAL_EXEC_TOTAL_TIMEOUT,
            total=self.APPROVAL_EXEC_TOTAL_TIMEOUT,
        )
