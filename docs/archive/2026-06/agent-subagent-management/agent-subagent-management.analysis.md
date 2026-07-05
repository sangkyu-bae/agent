# agent-subagent-management — Gap Analysis (PDCA Check)

> **Date**: 2026-06-30
> **Design**: [agent-subagent-management.design.md](../02-design/features/agent-subagent-management.design.md)
> **Match Rate (initial)**: 98% → **100% after D-3 fix**

## Summary

| Bucket | Result |
|--------|--------|
| FR-01..08 | 8 / 8 Implemented (100%) |
| DD-1, DD-2 | 2 / 2 Implemented (100%) |
| §11 Implementation order | 12 / 12 done (100%) |
| Test groups present | 7 / 7 (100%) |
| Discrepancies | 3 (1 fixed: D-3; 2 accepted-minor: D-1, D-2) |

## Per-FR / Per-DD verification

| ID | Status | Evidence |
|----|:------:|----------|
| FR-01 섹션 + 관리 버튼 | ✅ | `idt_front/.../LeftConfigPanel.tsx:135-145` |
| FR-02 2-pane 모달 | ✅ | `SubAgentManagerModal.tsx` (grid-cols-2) |
| FR-03 owned+public+department | ✅ | `list_available_sub_agents_use_case.py` (`scope="all"`) |
| FR-04 self/기존 제외, DRAFT 포함 | ✅ | `SubAgentManagerModal.tsx:44-46`; repo `status != "deleted"` |
| FR-05 form→`sub_agent_configs` | ✅ | `LeftConfigPanel.tsx`; `AgentBuilderPage/index.tsx` |
| FR-06 edit add/remove | ✅ | `update_agent_use_case.py` + edit-load `index.tsx` |
| FR-07 3-max/cycle UI 가드 + 서버 에러 표면화 | ✅ | UI `SubAgentManagerModal.tsx`; 서버 검증 — D-3 보강 후 완전 |
| FR-08 모델 배지 + visibility/source | ✅ | `application/schemas.py`; `SubAgentManagerModal.tsx` |
| **DD-1** `VisibilityPolicy.can_access` 기반 | ✅ | `sub_agent_worker_builder.py` |
| **DD-2** `sub_agent_configs`+`replace_sub_agents`+repo sync | ✅ | `update_agent_use_case.py` → `domain/schemas.py` → `_sync_workers` |

API 엔드포인트, BE↔FE 계약, 7개 테스트 그룹 모두 존재 확인.

## Discrepancies

- **🟡 D-3 (Medium, security) — FIXED**: 설계 §4.4/§7가 요구한 `NestingDepthPolicy.validate_depth` + `CircularReferencePolicy.validate_no_cycle`(self + 하위 그래프)가 빌더에 누락. 직접 자기참조만 차단되어 간접 순환(A→B→A)·깊이 초과가 서버에서 막히지 않았음(UI 후보 필터에만 의존 → 클라이언트 우회 가능). → `SubAgentWorkerBuilder._validate_graph` 추가로 서버측 강제.
- **🟢 D-1 (Low) — accepted**: `SubAgentAccessPolicy`(policies.py)가 구독 기반으로 남아 dead code. 자체 테스트 보존을 위해 deprecation 주석 처리(삭제 시 `test_multi_agent_policies.py` 회귀).
- **🟢 D-2 (info) — accepted**: `CreateAgentUseCase`의 `subscription_repo` 주입이 게이트 제거 후 미사용. DI 호환을 위해 파라미터 유지(향후 정리).

## Architecture / Convention
- Clean Architecture 100% — domain 외부 의존 없음, 라우터 무로직, repository flush-only.
- Convention ~99% — 모달 패턴/PascalCase/계약 동기화 준수.

## Next
Match Rate ≥ 90% (D-3 보강 후 100%) → `/pdca report agent-subagent-management`.
