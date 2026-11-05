"""KbDefaultSetting — 지식베이스 자동 구성 전역 기본값.

agent-kb-quick-setup Design §3.1.

단일 행. default_embedding_model_id 는 embedding_model.id 소프트 참조.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class KbDefaultSetting:
    default_embedding_model_id: int | None
    updated_at: datetime | None = None

    @property
    def configured(self) -> bool:
        """모델 id 가 있는지만 본다 — 존재·활성 여부는 UseCase 가 모델 저장소로 판정."""
        return self.default_embedding_model_id is not None
