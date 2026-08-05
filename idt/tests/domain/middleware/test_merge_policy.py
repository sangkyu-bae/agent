"""builtin-middleware D1: MiddlewareMergePolicy 단위 테스트.

병합 규칙: 스냅샷 ∪ enforced, type 기준 dedupe, inactive 제외(카탈로그 게이트),
config는 카탈로그 default_config 단일 소스, sort_order 정렬.
"""
from src.domain.middleware.entities import (
    MiddlewareCatalogEntry,
    MiddlewareType,
)
from src.domain.middleware.policies import MiddlewareMergePolicy


def _entry(
    mw_type: MiddlewareType,
    *,
    is_builtin: bool = False,
    is_enforced: bool = False,
    is_active: bool = True,
    sort_order: int = 0,
    config: dict | None = None,
) -> MiddlewareCatalogEntry:
    return MiddlewareCatalogEntry(
        id=f"id-{mw_type.value}",
        middleware_type=mw_type,
        name=mw_type.value,
        description="",
        is_builtin=is_builtin,
        is_enforced=is_enforced,
        default_config=config or {},
        is_active=is_active,
        sort_order=sort_order,
    )


class TestMerge:
    def test_스냅샷_타입이_적용된다(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, sort_order=10)]
        applied = MiddlewareMergePolicy.merge(["model_retry"], catalog)
        assert [a.middleware_type for a in applied] == [MiddlewareType.MODEL_RETRY]

    def test_enforced는_스냅샷에_없어도_적용된다(self):
        catalog = [
            _entry(MiddlewareType.MODEL_CALL_LIMIT, is_enforced=True, sort_order=40),
        ]
        applied = MiddlewareMergePolicy.merge([], catalog)
        assert [a.middleware_type for a in applied] == [
            MiddlewareType.MODEL_CALL_LIMIT
        ]

    def test_스냅샷과_enforced_중복은_1회만(self):
        catalog = [
            _entry(MiddlewareType.MODEL_RETRY, is_enforced=True, sort_order=10),
        ]
        applied = MiddlewareMergePolicy.merge(["model_retry"], catalog)
        assert len(applied) == 1

    def test_inactive_카탈로그는_스냅샷이어도_제외(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, is_active=False)]
        applied = MiddlewareMergePolicy.merge(["model_retry"], catalog)
        assert applied == []

    def test_inactive_enforced도_제외(self):
        catalog = [
            _entry(MiddlewareType.TOOL_RETRY, is_enforced=True, is_active=False),
        ]
        applied = MiddlewareMergePolicy.merge([], catalog)
        assert applied == []

    def test_카탈로그에_없는_스냅샷_타입은_제외(self):
        applied = MiddlewareMergePolicy.merge(["model_retry"], [])
        assert applied == []

    def test_미지_문자열_스냅샷은_무시(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY)]
        applied = MiddlewareMergePolicy.merge(["없는타입"], catalog)
        assert applied == []

    def test_sort_order_정렬(self):
        catalog = [
            _entry(MiddlewareType.MODEL_CALL_LIMIT, is_enforced=True, sort_order=40),
            _entry(MiddlewareType.MODEL_RETRY, sort_order=10),
        ]
        applied = MiddlewareMergePolicy.merge(["model_retry"], catalog)
        assert [a.middleware_type for a in applied] == [
            MiddlewareType.MODEL_RETRY,
            MiddlewareType.MODEL_CALL_LIMIT,
        ]

    def test_config는_카탈로그_default_config(self):
        catalog = [
            _entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5}),
        ]
        applied = MiddlewareMergePolicy.merge(["model_retry"], catalog)
        assert applied[0].config == {"max_retries": 5}
