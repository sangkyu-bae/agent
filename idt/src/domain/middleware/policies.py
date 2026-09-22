"""builtin-middleware D1: 미들웨어 병합 정책."""
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    AppliedMiddleware,
    MiddlewareCatalogEntry,
)


class MiddlewareMergePolicy:
    """스냅샷 ∪ enforced 병합 — 실행 시 적용 목록의 단일 결정 지점.

    - 카탈로그가 게이트: inactive/미등록 타입은 스냅샷에 있어도 제외.
    - enforced(active)는 스냅샷과 무관하게 포함 (사용자가 빼도 적용).
    - type 기준 dedupe(중복 1회).
    - config = 카탈로그 default_config ∪ 에이전트 record.config (record 우선).
      approval-gate Design §3.4 — 이전에는 default_config 단일 소스였고
      record.config 는 "후속 오버라이드 예약" 상태로 버려지고 있었다.
      에이전트마다 다른 집행 시각(금리 00시)이 필요해지며 구현했다.
    - 카탈로그 sort_order 오름차순 정렬 (미들웨어 체인 순서).
    """

    @staticmethod
    def merge(
        records: list[AgentMiddlewareRecord],
        catalog: list[MiddlewareCatalogEntry],
    ) -> list[AppliedMiddleware]:
        active = {e.middleware_type.value: e for e in catalog if e.is_active}
        overrides = {
            r.middleware_type: (r.config or {})
            for r in records
            if r.middleware_type in active
        }
        applied_types = set(overrides) | {
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
                # dict(...) 로 복사한다 — 결과를 수정해도 카탈로그 원본이
                # 오염되면 같은 요청 내 다음 에이전트까지 번진다.
                config={
                    **dict(e.default_config),
                    **overrides.get(e.middleware_type.value, {}),
                },
                sort_order=e.sort_order,
                is_enforced=e.is_enforced,
            )
            for e in entries
        ]
