"""도메인 스키마: AgentOpener — 에이전트별 대화 시작 예시 질문 1건.

Design Ref: agent-opener §3.1. 리포지토리 내부 매핑용 — 소비자(API·채팅·포크)는
텍스트 배열(list[str])만 다룬다.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AgentOpener:
    id: str
    agent_id: str
    text: str
    sort_order: int = 0
    created_at: datetime | None = None
