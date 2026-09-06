# Agent Update Tool Editing Gap Analysis

> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Date**: 2026-09-06
> **Analyst**: 배상규
> **Design Doc**: [agent-update-tool-editing.design.md](../02-design/features/agent-update-tool-editing.design.md)
> **Plan Doc**: [agent-update-tool-editing.plan.md](../01-plan/features/agent-update-tool-editing.plan.md)
> **Overall Match Rate**: **98%** (정적 전용 공식 — 런타임 축 미실행)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 수정 API 가 도구 구성을 못 바꿔 도구 변경이 조용히 유실되고, 발표자료 설정은 422 로 실패한다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자 |
| **RISK** | 워커 전량 재구성이 종속 데이터·visibility scope 를 깨뜨릴 수 있음 |
| **SUCCESS** | 도구 추가/삭제가 PATCH 한 번으로 반영, 유지 도구 config 보존, 제거 시 soft-delete |
| **SCOPE** | M1~M5 전 모듈 구현 완료 |

---

## 0. 분석 수행 방식 (투명성 고지)

`gap-detector` 서브에이전트를 2회 기동했으나 **두 번 모두 본문·파일 산출 없이 종료**하여
(1차: 응답 본문 유실, 2차: 지정 경로에 파일 미생성) 독립 검증분을 확보하지 못했다.
따라서 **이 분석은 구현자 자신의 코드 재검증**이며, 독립 리뷰어의 교차 확인은 받지 않았다.
근거는 모두 `file:line` 으로 명시했으므로 재현 검증이 가능하다.

**런타임 검증(L1/L2/L3) 미실행**: 백엔드 서버 미기동 + 이 기능의 Playwright 자산 없음.
Match Rate 는 정적 전용 공식 `Structural×0.2 + Functional×0.4 + Contract×0.4` 로 산출.

---

## Strategic Alignment Check

### Plan Success Criteria Status

| SC | 내용 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 발표자료생성기 미보유 에이전트 도구 추가 + 양식 저장 성공 (원 결함) | ✅ Met | `test_update_agent_tool_editing.py::test_t02_adding_presentation_generator_with_config_succeeds` |
| SC-2 | 도구 제거 시 워커 행 소멸 + 실행 그래프 제외 | ✅ Met | `test_t03_removed_tool_disappears_and_sort_order_is_compacted` + `agent_definition_repository.py:135-159` |
| SC-3 | RAG 유지 시 기존 tool_config(kb_id) 보존 | ✅ Met | `test_t04_kept_tool_inherits_existing_config_when_not_sent` / `update_agent_use_case.py:300-309` |
| SC-4 | 문서생성기 제거 시 종속 레코드 soft-delete | ✅ Met | `test_t06_...` / `test_t07_...` / `test_kept_document_generator_is_not_soft_deleted` |
| SC-5 | tool_ids 미전송 = 도구 구성 무변경 | ✅ Met | `test_t01_omitting_tool_ids_leaves_workers_untouched` + agent_builder 974건 무회귀 |
| SC-6 | public + private KB 도구 → clamp + 응답 통지 | ✅ Met | `test_t16_adding_personal_kb_tool_clamps_public_visibility` |
| SC-7 | MCP 도구 추가/삭제가 내부 도구와 동일 동작 | ✅ Met | `test_t11_/t12_/t13_` |

**Success Rate: 7/7 (100%)**

### PRD/Plan Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| 핵심 문제(도구 변경의 조용한 유실)를 풀었는가 | ✅ | `tool_ids` 계약 + `_rebuild_tool_workers`. 추가로 `tool_configs` 단독 전송을 422 로 차단(`update_agent_use_case.py:181-184`)해 동일 형태 재발을 막음 |
| 주인공 P2 관점에서 가치가 있는가 | ✅ | 에이전트 재생성 없이 도구 구성 진화 가능 |
| 일반화 vs 특화 원칙 | ✅ | 특정 도구 하드코딩 없음. 종속 정리만 도구별 매핑(`_cleanup_removed_tool_deps`)이며 확장 가능한 튜플 구조 |

### Decision Record Verification

| 결정 | 출처 | 준수 | 근거 |
|------|------|:----:|------|
| A안 — 근본 해결(수정 API 에 도구 편집 추가) | Plan | ✅ | `UpdateAgentRequest.tool_ids/tool_configs` (`schemas.py:150-157`) |
| Option C — 빌더 공용 모듈 추출 | Design §2.0 | ✅ | `worker_skeleton_builder.py` 신규, create 는 위임만(-211줄) |
| 목표 상태 전체 교체 계약 | Design §7.2 | ✅ | None/[]/[...] 3분기 |
| 기존 config 보존 머지 | Design §7.2 | ✅ | `_inherit_tool_configs` |
| 종속 soft-delete | Design §7.2 | ✅ | `_cleanup_removed_tool_deps` |
| 빌트인 생성과 동일 규칙 재주입 | Design §7.2 | ✅ | `build_builtin_workers` 공유 |
| MCP 동등 지원 | Design §7.2 | ✅ | `mcp_server_repo` DI (`main.py:2931-2933`) |
| DB 마이그레이션 불필요 | Design §7.2 | ✅ | 스키마 변경 0 |
| 명시 visibility=422 / 자동 clamp 분리 | Design §7 | ✅ | `_apply_scope_clamp:325-329` vs `:331-345` |

---

## 1. Analysis Overview

### 1.1 Purpose

Design 문서 §2~§11 대비 구현 코드의 구조·기능·계약 일치도를 측정하고 잔여 Gap 을 목록화한다.

### 1.2 Scope

백엔드 6파일 + 프론트 3파일 + 테스트 6파일. 런타임 축 제외.

---

## 2. Gap Analysis

### 2.1 파이프라인 순서 검증 (Design §2.2)

| 설계 순서 | 코드 실제 | 일치 |
|---|---|:---:|
| ① 워커 재구성 | `update_agent_use_case.py:177` → `:258` build_from_tool_ids | ✅ |
| ② 종속 정리 | `:285` `_cleanup_removed_tool_deps` | ⚠️ 위치 상이 |
| ③ scope clamp | `:296` `_apply_scope_clamp` | ✅ |
| ④ 정책 검증 | `:264-268` (설계보다 **앞**) | ⚠️ 위치 상이 |
| ⑤ 문서/발표자료 바인딩 | `:206`, `:211`, `:217` (재구성 이후) | ✅ |
| ⑥ save | `:221` | ✅ |

**핵심 불변식은 충족**: 재구성(177) < 바인딩(217) < save(221) — 원 결함 해소 조건.
정책 검증만 종속 정리보다 앞으로 이동했다(fail-fast: 상한 위반 시 soft-delete 를 수행하지 않음).
동작상 이점이 있으나 **설계 문서의 순서 표기와 어긋나므로 문서 동기화가 필요**하다.

### 2.2 의미론 매트릭스 검증 (Design §4.2)

| tool_ids | tool_configs | 설계 기대 | 구현 | 테스트 |
|---|---|---|:---:|---|
| None | None | 무변경 | ✅ `:176` | T-01 |
| None | 값 | **422** | ✅ `:181-184` | T-14 |
| [] | 무관 | 전부 해제 + 빌트인 재주입 | ✅ | T-09 |
| [...] | None | 교체 + 설정 승계 | ✅ | T-04 |
| [...] | 값 | 교체 + 전달분 덮어쓰기 | ✅ | T-05 |

**5/5 반영 (100%)**

### 2.3 기능 요구사항 이행 (Plan §3.1)

| FR | 상태 | 근거 |
|----|:----:|------|
| FR-01 None=무변경 | ✅ | `update_agent_use_case.py:176` |
| FR-02 목표 상태 전체 교체 | ✅ | `:258` + `replace_tool_workers` |
| FR-03 config 승계 | ✅ | `:300-309` `_inherit_tool_configs` |
| FR-04 종속 soft-delete | ✅ | `:377-390` |
| FR-05 서브에이전트 보존·재배치 | ✅ | `domain/agent_builder/schemas.py:170-185` |
| FR-06 scope 재검증 + clamp | ✅ | `:311-352` |
| FR-07 워커 개수 재검증 | ✅ | `:264-268` |
| FR-08 MCP 동등 지원 | ✅ | `worker_skeleton_builder.py:165-190` + DI |
| FR-09 빌트인 재주입 | ✅ | `worker_skeleton_builder.py:118-155` |
| FR-10 재구성이 바인딩 이전 | ✅ | 177 < 206/211/217 |
| FR-11 worker_id 결정론 | ✅ | `worker_skeleton_builder.py:33-41` |
| FR-12 프론트 payload | ✅ | `agentToolPayload.ts` + `index.tsx` 수정 분기 |
| FR-13 응답 clamp 통지 | ✅ | `schemas.py:190-196` + `index.tsx` onSuccess |

**13/13 (100%)**

### 2.4 API Contract Verification (3-way)

| 항목 | Design §4.2 | 서버 | 클라이언트 | 일치 |
|---|---|---|---|:---:|
| `tool_ids` | `list[str] \| None` | `schemas.py:150` | `agentBuilder.ts` `tool_ids?: string[]` | ✅ |
| `tool_configs` | `dict \| None` | `schemas.py:157` | `Record<string, RagToolConfig>` | ✅ |
| `visibility` | 응답 | `schemas.py:192` | `visibility?: string` | ✅ |
| `visibility_clamped` | 응답 | `schemas.py:193` | `visibility_clamped?: boolean` | ✅ |
| `max_visibility` | 응답 | `schemas.py:194` | `max_visibility?: string \| null` | ✅ |
| 에러 매핑 422/409/403 | §6.1 | `agent_builder_router.py:262-267` | 메시지 표시 | ✅ |

**Contract 100%** — 프론트 응답 필드를 전부 optional 로 둬 구 서버 응답과도 호환.

### 2.5 테스트 커버리지 (Design §8.2/§8.3)

| 계층 | 계획 | 구현 | 비고 |
|---|---|---|---|
| L1 백엔드 T-01~T-18 | 18 | **18/18** | `test_update_agent_tool_editing.py` (22건 — 시나리오 외 4건 추가) |
| 빌더 단위 | — | 17 | `test_worker_skeleton_builder.py` |
| 스키마 계약 | — | 5 | `test_update_agent_tool_fields.py` |
| 도메인 | — | 4 | `test_replace_tool_workers.py` |
| L2 프론트 F-01~F-04 | 4 | **4/4** (+2 변형) | `agentToolPayload.test.ts` 5, `index.test.tsx` 6 |
| L3 E2E | 수동 | ❌ 미실행 | 서버 미기동 |

### 2.6 Match Rate Summary

| 축 | 매치율 | 산출 근거 |
|---|:---:|---|
| **Structural** | 100% | Design §11.1 파일 11항목 전부 존재 (1건은 승인된 대체) |
| **Functional** | 95% | FR 13/13 + 매트릭스 5/5 충족. Minor 2건 감점 |
| **API Contract** | 100% | 3-way 6항목 전부 일치 |
| **Runtime** | — | 미실행 (서버 부재) |

```
Overall = (100 × 0.2) + (95 × 0.4) + (100 × 0.4) = 98%
```

---

## 3. Gap 목록

| # | Severity | Confidence | 내용 | 위치 | 권고 |
|---|---|---|---|---|---|
| G-1 | Minor | 95% | 설계 §6.1 의 전용 에러 메시지 `"MCP 도구 수정 구성이 초기화되지 않았습니다 (mcp_server_repo 미주입)."` 미구현 — `Unknown tool_id: '...'` 로 폴백 | `worker_skeleton_builder.py:191` | 메시지 보강 또는 설계에서 항목 삭제. 422 매핑·안전성은 이미 충족(T-13) |
| G-2 | Minor | 100% | 정책 검증 위치가 설계 §2.2 순서표(④)와 다름 — 코드는 종속 정리보다 앞(fail-fast) | `update_agent_use_case.py:264-268` | **문서를 코드에 맞춰 갱신** 권장 (코드가 더 안전) |
| G-3 | Info | 100% | 수정 경로는 `exclude_builtin_tool_ids` 채널이 없어, 생성 시 제외했던 빌트인이 도구 편집 저장 시 재주입됨 | `_rebuild_tool_workers` → `build_builtin_workers(…, None, …)` | 승인된 의미론(빌트인 opt-out 은 생성 전용 채널). 위키/설계에 명시만 하면 충분 |

### 승인된 설계 이탈 (Gap 아님)

| 항목 | 내용 |
|---|---|
| D-1 | 설계 §5.1 "mapDetailToForm 빌트인 제외" → 전송 시점 필터 `buildToolIdsForSave` 로 대체. edit 모드 칩 UI(`LeftConfigPanel.tsx:174-181`) 보존 + `MAX_TOOLS` 왜곡 제거 |
| D-2 | `repository.update()` 의 `flow_hint` 영속 추가 — 설계에 없던 항목이나 구현 중 발견한 기존 결함(도구 변경 시 supervisor 프롬프트가 옛 도구 체인 참조) |
| D-3 | `make_worker_id` 3곳 통일 — 설계 §10.4 에 명시된 정합 정리 |
| D-4 | clamp 결과가 `department` 인데 `department_id` 가 없으면 `private` 까지 하향 — 설계 미기재 경계, 도메인 불변식 정합 목적 |

---

## 4. Clean Architecture Compliance

| 규칙 | 준수 | 근거 |
|---|:---:|---|
| domain → infrastructure 참조 없음 | ✅ | `replace_tool_workers` 는 순수 리스트 조작 |
| application 이 repo 인터페이스만 의존 | ✅ | `WorkerSkeletonBuilder` 는 repo 를 생성자 주입으로만 받음 |
| Repository 내부 commit/rollback 없음 | ✅ | soft-delete 는 동일 세션 편승 |
| 함수 40줄 / if 2단계 | ✅ | `_rebuild_tool_workers` 는 4개 헬퍼로 분할 |
| print 금지 / 구조화 로깅 | ✅ | `added_tool_ids`/`removed_tool_ids` info 로깅 |

---

## 5. 결론

원 결함(`presentation_generator` 워커 부재 422)의 근본 원인인 "수정 API 의 도구 편집 부재"가
해소됐고, Success Criteria 7/7 · FR 13/13 · 계약 3-way 6/6 이 충족됐다.
잔여 Gap 3건은 모두 Minor/Info 이며 **동작 결함이 아니라 문서 동기화·메시지 품질 사안**이다.

다만 두 가지를 분명히 남긴다:
1. **런타임 검증 미실행** — 실제 서버 왕복(도구 추가 저장 → 재진입 프리필 → 실행 그래프 반영)은
   확인하지 않았다. `/pdca qa` 또는 수동 시나리오로 보완이 필요하다.
2. **독립 검증 부재** — gap-detector 산출 실패로 구현자 자기검증에 그쳤다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-06 | 초안 — 정적 3축 98%, Gap 3건(Minor 2 / Info 1), 승인 이탈 4건 | 배상규 |
