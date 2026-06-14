"""AgentRun 애플리케이션 DTO 및 설정.

AGENT-OBS-001 §3-2 RunObservabilityConfig — 관측성 모듈 공통 설정.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RunObservabilityConfig:
    """관측성 모듈 설정. 모든 하드코딩 금지 (CLAUDE.md §3)."""

    pricing_cache_ttl_seconds: int = 300  # 가격 캐시 TTL (5분)
    summary_text_max_bytes: int = 1024     # input/output_summary 컷오프
    retrieval_preview_max_bytes: int = 500
    best_effort_log_level: str = "warning"
