"""builtin-middleware D1: 미들웨어 병합 정책."""
from src.domain.middleware.entities import (
    AppliedMiddleware,
    MiddlewareCatalogEntry,
)


class MiddlewareMergePolicy:
    """스냅샷 ∪ enforced 병합 — 실행 시 적용 목록의 단일 결정 지점.

    - 카탈로그가 게이트: inactive/미등록 타입은 스냅샷에 있어도 제외.
    - enforced(active)는 스냅샷과 무관하게 포함 (사용자가 빼도 적용).
    - type 기준 dedupe(중복 1회), config는 카탈로그 default_config 단일 소스.
    - 카탈로그 sort_order 오름차순 정렬 (미들웨어 체인 순서).
    """

    @staticmethod
    def merge(
        snapshot_types: list[str],
        catalog: list[MiddlewareCatalogEntry],
    ) -> list[AppliedMiddleware]:
        active = {
            e.middleware_type.value: e for e in catalog if e.is_active
        }
        applied_types: set[str] = {
            t for t in snapshot_types if t in active
        }
        applied_types |= {
            e.middleware_type.value
            for e in catalog
            if e.is_enforced and e.is_active
        }
        entries = sorted(
            (active[t] for t in applied_types), key=lambda e: e.sort_order
        )
        return [
            AppliedMiddleware(
                middleware_type=e.middleware_type,
                config=dict(e.default_config),
                sort_order=e.sort_order,
            )
            for e in entries
        ]
