"""agent_alert 도메인 엔티티 — 에이전트별 알림 수신 설정과 수신 이력.

Design Ref: firewall-agent design §3.1. 시각은 UTC naive.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AlertReceiptResult = Literal[
    "enqueued",  # 백그라운드 잡 등록
    "duplicate",  # 같은 그룹·같은 발화 집합 재전송
    "resolved_only",  # 발화(firing) 알림 없음
    "disabled",  # 수신 꺼짐
    "skipped_busy",  # 진행 중·승인 대기 건 존재 (skip_reason 동반)
    "invalid_payload",  # JSON 아님·alerts 없음
]


@dataclass
class AlertReceiver:
    id: str
    agent_id: str
    user_id: str  # 설정자 = 실행 신원 (백그라운드 잡 user_id)
    enabled: bool
    skip_when_busy: bool
    token_hash: str
    token_hint: str
    instruction_prefix: str
    created_at: datetime
    updated_at: datetime


@dataclass
class AlertReceipt:
    id: str
    receiver_id: str
    agent_id: str
    group_key_hash: str
    fingerprints_hash: str
    firing_count: int
    result: AlertReceiptResult
    skip_reason: str | None
    job_id: str | None
    received_at: datetime
    request_id: str
