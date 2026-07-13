# kb-rag-filter Design-Implementation Gap Analysis

> **Analyzer**: bkit:gap-detector
> **Date**: 2026-07-09 (Act-1 재검증: 2026-07-10)
> **Design**: `docs/02-design/features/kb-rag-filter.design.md`

## 요약

| 항목 | 값 |
|------|-----|
| Match Rate | **97.6%** (20.5 / 21 판정 항목) — Act-1 후 (초기 92.9%) |
| Match | 20 · Partial 0 · Missing 1 |
| 순수 Gap 개수 | 1 (Missing 1 — G2 E2E 수동검증, 기지) |
| 핵심 Gap | ~~D3 읽기권한 403 미구현~~ → **Act-1에서 해소**. 잔여: §7 E2E 수동검증(기지) |
| 상태 | 코드 레벨 설계 일치 우수 — 저장/실행 배선·clamp·403·프론트·테스트 전건 구현. 잔여는 수동 검증뿐 |

97.6% ≥ 90% → report 진입 가능.

## Act-1 반복 결과 (2026-07-10)

**G1 해소 — D3: Partial → Match.** TDD(Red 10건 → Green)로 구현, gap-detector 재검증 완료.

| 변경 | 내용 |
|------|------|
| `src/domain/knowledge_base/policy.py` | `can_read_ref(user_id, role, kb, dept_ids)` 신설, `can_read`는 위임(규칙 단일 소스) |
| `src/application/agent_builder/create_agent_use_case.py` | `_resolve_kbs`가 요청자(user_id, viewer_role) 수취 → 존재 검증 후 `can_read_ref` 실패 시 `PermissionError("No read access to knowledge base '...'")`. admin은 부서 조회 생략 |
| `src/application/agent_builder/update_agent_use_case.py` | `_lookup_kb_scopes` 동일 검증. `_validate_visibility_scope`가 `viewer_user_id or agent.user_id` + `viewer_role` 전달 |
| `src/api/routes/agent_builder_router.py` | update 403 detail을 고정 문구 대신 `str(e)`로 전달(KB 거부 사유 표면화) — create는 기존대로 `str(e)` |
| 테스트 | 도메인 `TestCanReadRef` 7건 + create 3건(타인 PERSONAL 403 / 미소속 DEPARTMENT 403 / admin 통과) + update 2건(타인 PERSONAL 403 / admin 통과). 회귀 740건 전부 통과 (MCPRouting 3건은 기지 Windows 이벤트루프 이슈로 제외) |

**재검증 시 관찰(비차단)**:
- update는 `visibility` 변경 시에만 KB 재검증 — update가 도구 워커를 재배선하지 않으므로 저장시점 검증 의도(D3)와 정합. 접근권 상실 후 이름만 변경하는 경우 재검증 없음(수용).
- `_owner_ref`는 비정수 user_id를 소유자 불일치로 처리 — 현 시스템(정수 문자열 id)에서 무해.

## 항목별 판정

### §3 결정사항 (D1~D7)

| ID | 설계 요구 | 구현 위치 | 판정 |
|----|-----------|-----------|:----:|
| D1 | 저장 시점 물리 컬렉션 고정(canonicalize) | `create_agent_use_case._canonicalize_kb_collections` (`collection_name = kbs[kb_id].collection_name`) | Match |
| D2 | kb_id 우선 규칙 + UI 컬렉션 disabled | `tool_factory._merge_kb_filter` (`{**metadata_filter, "kb_id": kb_id}`) / `RagConfigPanel` 컬렉션 `disabled={!!config.kb_id}` + 안내문 | Match |
| D3 | 미존재→ValueError(400), **권한없음→PermissionError(403)** | 미존재 `ValueError` + **Act-1: `can_read_ref` 기반 `PermissionError(403)` 구현** (`_resolve_kbs`/`_lookup_kb_scopes`) | **Match** |
| D4 | KB 목록 API 재사용 + 권한 필터 | `knowledge_base_router.py:213` `list_knowledge_bases` → `use_case.list(current_user)` | Match |
| D5 | kb_id 형식 검증 안 함 | `RagToolConfig.kb_id` VO 무검증, `__post_init__`/`Policy` 무변경 | Match |
| D6 | ToolFactory 병합, InternalDocumentSearchTool 무수정 | `tool_factory._merge_kb_filter` → `effective_filter` 전달, 도구 시그니처 무변경 | Match |
| D7 | scope clamp 확장 + kb_repo None 명시 에러 | create/update 양쪽 `_resolve_kbs`/`_lookup_kb_scopes`가 kb_repo None 시 `ValueError` 발생(조용한 skip 없음) | Match |

### §4 Backend

| § | 요구 | 구현 | 판정 |
|---|------|------|:----:|
| 4.1 | `RagToolConfig.kb_id: str\|None=None` | `rag_tool_config.py:49` | Match |
| 4.2 | `RagToolConfigRequest.kb_id` | `schemas.py:40` | Match |
| 4.3 | create UseCase 확장(resolve/canonicalize/visibility/extract 제외) | `_resolve_kbs`, `_canonicalize_kb_collections`, `_resolve_visibility`(kb_scopes 합류), `_extract_collection_names`(kb_id 워커 제외) | Match |
| 4.4 | update UseCase 확장 | `_lookup_kb_scopes`, `_validate_visibility_scope`(kb 제외 + kb scope 합류) | Match |
| 4.5 | ToolFactory 병합 | `_merge_kb_filter` | Match |
| 4.6 | main.py DI(kb_repo) | `create_uc_factory`/`update_uc_factory`에 `_make_kb_repo(session)` 주입(동일 세션) | Match |
| 4.7 | 무변경 명시(도구/검색경로/스키마) | 마이그레이션 없음, tool 무수정 확인 | Match |

### §5 Frontend

| § | 요구 | 구현 | 판정 |
|---|------|------|:----:|
| 5.1 | `RagToolConfig.kb_id` + `KnowledgeBaseInfo` | `types/ragToolConfig.ts:15,21` | Match |
| 5.2 | 상수/서비스/훅/queryKey | `KNOWLEDGE_BASES`(api.ts), `knowledgeBaseService`(envelope `knowledge_bases` 매핑, 백엔드 `KbListResponse`와 일치), `useKnowledgeBases`(staleTime 5분), `queryKeys.knowledgeBases.list` | Match |
| 5.3 | KB 드롭다운/컬렉션 disabled/scope 안내/메타키 연동 | `RagConfigPanel` Section 0 신설, disabled, 개인·부서 안내, `useMetadataKeys(selectedKb.collection_name)` | Match |
| 5.4 | 요약 배지 KB 라벨 최우선 + 데이터 전달 | `RagConfigSummaryBadge` kbLabel 우선, `LeftConfigPanel` `knowledgeBases` prop 전달 | Match |

### §6 테스트 (설계 목록 ↔ 실제)

| 파일 | 설계 요구 | 실제 | 판정 |
|------|:--------:|:----:|:----:|
| `test_rag_tool_config.py` (kb_id) | 4 | 4 (default_none, restored_from_legacy, roundtrip, no_format_validation) | Match |
| `test_tool_factory.py` `TestToolFactoryKbFilter` | 5 | 5 (merged, merges_with_existing, first_class_overrides, without_kb_unchanged, legacy_restores_none) | Match |
| `test_create_agent_use_case.py` `TestKbRagFilter` | 8 | 8 (personal/department/public clamp, canonicalize, skip_collection_lookup, unknown_raises, without_repo_raises, existing_flow_unchanged) | Match |
| `test_update_agent_use_case.py` `TestUpdateVisibilityKbScope` | 5 | 5 (personal_blocks_public, public_allows, worker_not_looked_up, missing_raises, without_repo_raises) | Match |
| `useKnowledgeBases.test.ts` | 2 | 2 (목록 반환, 실패 isError) | Match |
| `RagConfigPanel.test.tsx` (지식베이스 describe) | 6 | 6 (라벨/scope, 선택 시 초기화, disabled+안내, 개인 제한, 공개 미표시, 해제 undefined) | Match |
| `RagConfigSummaryBadge.test.tsx` | 3 | 3 (KB 이름, 미존재 시 원문, 없으면 컬렉션 로직) | Match |

테스트 케이스 수는 설계 §6 목록과 전건 정확히 대응.

### §7 구현 순서

| 단계 | 판정 |
|------|:----:|
| BE-1~4, FE-1~3 | Match (§4·§5 전건 구현 확인) |
| [E2E] 수동 검증(step 8) | **Missing (기지 — 별도 표기)** |

## Gap 목록

| # | Gap | 설계 참조 | 심각도 | 설명 |
|---|-----|-----------|:------:|------|
| ~~G1~~ | ~~KB 읽기권한 403 미구현~~ | §3 D3 | ~~Medium~~ | **Act-1(2026-07-10)에서 해소** — 상단 "Act-1 반복 결과" 참조. |
| G2 | E2E 수동 검증 미수행 | §7 step8, §9 | Low(기지) | KB A/B 격리 검색·clamp 실측 미완. 사용자 사전 고지된 항목으로 코드 회귀 아님. Qdrant payload `kb_id` 일치 실측 필요. |

## 권고사항

### 즉시 조치
1. ~~**G1**~~: Act-1에서 완료 — `can_read_ref` 권한 검증 + `PermissionError(403)` + 회귀 테스트 12건.

### 문서 업데이트
2. **G2**: E2E 수행 후 §9 Acceptance 체크박스 갱신 또는 analysis에 실측 결과 기록. 미수행 상태로 report 진입 시 "수동 검증 pending" 명기.

### 유지 권장 (무회귀 확인됨)
3. `kb_id=None` 경로 전건 무진입(FR-06) — VO 기본값·`_merge_kb_filter` early return·`_extract_collection_names` skip 로직으로 보장. 기존 에이전트 영향 없음.
