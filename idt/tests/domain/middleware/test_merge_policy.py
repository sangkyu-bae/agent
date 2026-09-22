"""builtin-middleware D1: MiddlewareMergePolicy 단위 테스트.

병합 규칙: 스냅샷 ∪ enforced, type 기준 dedupe, inactive 제외(카탈로그 게이트),
sort_order 정렬.

approval-gate Design §3.4: config 는 `카탈로그 default_config ∪ 에이전트
record.config`(record 우선) 로 바뀌었다. 기존 4종은 record.config 가 비어
있어 default_config 그대로다 — 무회귀를 아래 테스트가 고정한다.
"""
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
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


def _rec(mw_type: str, *, config: dict | None = None) -> AgentMiddlewareRecord:
    return AgentMiddlewareRecord(
        agent_id="a1", middleware_type=mw_type, sort_order=0, config=config
    )


class TestMerge:
    def test_스냅샷_타입이_적용된다(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, sort_order=10)]
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], catalog)
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
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], catalog)
        assert len(applied) == 1

    def test_inactive_카탈로그는_스냅샷이어도_제외(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, is_active=False)]
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], catalog)
        assert applied == []

    def test_inactive_enforced도_제외(self):
        catalog = [
            _entry(MiddlewareType.TOOL_RETRY, is_enforced=True, is_active=False),
        ]
        applied = MiddlewareMergePolicy.merge([], catalog)
        assert applied == []

    def test_카탈로그에_없는_스냅샷_타입은_제외(self):
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], [])
        assert applied == []

    def test_미지_문자열_스냅샷은_무시(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY)]
        applied = MiddlewareMergePolicy.merge([_rec("없는타입")], catalog)
        assert applied == []

    def test_sort_order_정렬(self):
        catalog = [
            _entry(MiddlewareType.MODEL_CALL_LIMIT, is_enforced=True, sort_order=40),
            _entry(MiddlewareType.MODEL_RETRY, sort_order=10),
        ]
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], catalog)
        assert [a.middleware_type for a in applied] == [
            MiddlewareType.MODEL_RETRY,
            MiddlewareType.MODEL_CALL_LIMIT,
        ]

    def test_config는_카탈로그_default_config(self):
        catalog = [
            _entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5}),
        ]
        applied = MiddlewareMergePolicy.merge([_rec("model_retry")], catalog)
        assert applied[0].config == {"max_retries": 5}


class TestPerAgentConfigOverride:
    """approval-gate Design §3.4 — record.config 가 default_config 를 덮는다."""

    def test_record_config가_default를_덮는다(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5})]
        applied = MiddlewareMergePolicy.merge(
            [_rec("model_retry", config={"max_retries": 1})], catalog
        )
        assert applied[0].config == {"max_retries": 1}

    def test_부분_오버라이드는_나머지_default를_보존한다(self):
        catalog = [
            _entry(
                MiddlewareType.MODEL_RETRY,
                config={"max_retries": 5, "backoff_factor": 2.0},
            )
        ]
        applied = MiddlewareMergePolicy.merge(
            [_rec("model_retry", config={"max_retries": 1})], catalog
        )
        assert applied[0].config == {"max_retries": 1, "backoff_factor": 2.0}

    def test_record_config가_None이면_default_그대로(self):
        """기존 4종 무회귀 — 지금까지 저장된 행은 config 가 비어 있다."""
        catalog = [_entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5})]
        applied = MiddlewareMergePolicy.merge(
            [_rec("model_retry", config=None)], catalog
        )
        assert applied[0].config == {"max_retries": 5}

    def test_record_config가_빈_dict여도_default_그대로(self):
        catalog = [_entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5})]
        applied = MiddlewareMergePolicy.merge(
            [_rec("model_retry", config={})], catalog
        )
        assert applied[0].config == {"max_retries": 5}

    def test_enforced만으로_적용된_건은_default_config(self):
        """스냅샷 record 가 없으므로 오버라이드할 것도 없다."""
        catalog = [
            _entry(
                MiddlewareType.APPROVAL_GATE,
                is_enforced=True,
                config={"mode": "always", "expires_hours": 168},
            )
        ]
        applied = MiddlewareMergePolicy.merge([], catalog)
        assert applied[0].config == {"mode": "always", "expires_hours": 168}

    def test_오버라이드가_카탈로그_default를_변형하지_않는다(self):
        """병합 결과를 수정해도 카탈로그 원본이 오염되면 다음 에이전트가 오염된다."""
        entry = _entry(MiddlewareType.MODEL_RETRY, config={"max_retries": 5})
        MiddlewareMergePolicy.merge(
            [_rec("model_retry", config={"max_retries": 1})], [entry]
        )
        assert entry.default_config == {"max_retries": 5}

    def test_승인게이트_에이전트별_집행시각_오버라이드(self):
        """금리 시나리오 — 이 에이전트만 00시 집행."""
        catalog = [
            _entry(
                MiddlewareType.APPROVAL_GATE,
                config={"mode": "always", "execute_after": None,
                        "expires_hours": 168},
                sort_order=100,
            )
        ]
        applied = MiddlewareMergePolicy.merge(
            [_rec("approval_gate",
                  config={"execute_after": "0 0 * * *", "expires_hours": 24})],
            catalog,
        )
        assert applied[0].config == {
            "mode": "always", "execute_after": "0 0 * * *", "expires_hours": 24,
        }


class TestIsEnforcedPropagation:
    """approval-gate — 런타임에 강제 여부를 알아야 mode=off 를 이길 수 있다."""

    def test_enforced_플래그가_결과에_실린다(self):
        catalog = [_entry(MiddlewareType.APPROVAL_GATE, is_enforced=True)]
        applied = MiddlewareMergePolicy.merge([], catalog)
        assert applied[0].is_enforced is True

    def test_비강제는_False(self):
        catalog = [_entry(MiddlewareType.APPROVAL_GATE)]
        applied = MiddlewareMergePolicy.merge([_rec("approval_gate")], catalog)
        assert applied[0].is_enforced is False
