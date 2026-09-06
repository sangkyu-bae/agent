# Agent Update Tool Editing 완료 보고서

> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Feature**: agent-update-tool-editing
> **Period**: 2026-09-05 ~ 2026-09-06
> **Author**: 배상규
> **Status**: Completed
> **Match Rate**: 98% · **QA**: PASS

---

## Executive Summary

### 1.1 Project Overview

에이전트 수정(PATCH) API 가 도구 구성을 변경할 수 없어 수정 화면의 도구 추가/삭제가
조용히 유실되고, `presentation_generator` 설정만 워커 부재로 422 를 내던 결함을
근본 해결했다. 수정 요청에 `tool_ids`/`tool_configs` 를 도입하고, UseCase 가 도구 워커를
목표 상태로 재구성한 뒤 문서/발표자료 바인딩을 수행하도록 파이프라인을 재배치했다.

### 1.2 Results Summary

| 지표 | 값 |
|---|---|
| Match Rate (정적 3축) | **98%** |
| QA 판정 | **QA_PASS** (L1 6/6, L2 11/11) |
| Success Criteria | **7/7 Met** |
| Functional Requirements | **13/13 구현** |
| 신규 테스트 | 백엔드 48건 + 프론트 11건 = **59건** |
| 무회귀 검증 | agent_builder 영향권 **1056건 통과** |
| 신규 파일 | 7 (구현 2 / 테스트 5) |
| 수정 파일 | 7 |
| 코드 증감 | +296 / -222 (신규 파일 1,300줄 별도) |
| DB 마이그레이션 | **0** |
| 반복(iterate) 횟수 | **0** — Check 첫 회 98% |

### 1.3 Value Delivered

| 관점 | 전달된 가치 (실측) |
|---|---|
| **Problem** | 수정 API 의 도구 편집 부재 → 도구 변경 유실 + 발표자료 설정 422. 실서버 재현 결과 **동일 요청이 422 → 200** 으로 복구 |
| **Solution** | 목표 상태 계약(`tool_ids`) + 6단계 재구성 파이프라인. 생성 경로의 빌드 규칙을 공용 모듈로 추출해 **규칙 이중화 제거**(create 경로 -211줄) |
| **Function/UX** | 수정 화면 도구 추가/삭제가 실제 반영. 유지 도구 설정 보존, 제거 도구 종속 데이터 soft-delete, 공개 범위 축소 시 사용자 안내 |
| **Core Value** | "생성 시점에 고정된 도구 구성" 제약 제거 — 에이전트를 재생성하지 않고 진화시킬 수 있게 되어 편집 계약이 생성 계약과 대칭을 이룸. 조용한 실패가 관측 가능한 성공/실패로 전환 |

---

## 1.4 Success Criteria Final Status

| SC | 내용 | 상태 | 증거 |
|----|------|:----:|------|
| SC-1 | 발표자료생성기 추가 + 양식 저장 성공 (원 결함) | ✅ Met | QA R1 **HTTP 200** (실서버) + `test_t02_...` |
| SC-2 | 도구 제거 시 워커 소멸 | ✅ Met | QA R3 (`tool_ids` 에서 제거 확인) + `test_t03_...` |
| SC-3 | 유지 도구 `tool_config` 보존 | ✅ Met | `test_t04_...`, `test_t05_...` |
| SC-4 | 제거 시 종속 레코드 soft-delete | ✅ Met | `test_t06_...`, `test_t07_...` |
| SC-5 | `tool_ids` 미전송 = 무변경 | ✅ Met | QA R5 + `test_t01_...` + 1056건 무회귀 |
| SC-6 | KB scope clamp + 응답 통지 | ✅ Met | `test_t16_...`, 프론트 F-04 |
| SC-7 | MCP 도구 동등 지원 | ✅ Met | `test_t11_/t12_/t13_` |

**Success Rate: 7/7 (100%)**

---

## 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|---|---|:---:|---|
| A안 — 수정 API 에 도구 편집 추가 (B: UI 차단 / C: 워커 자동생성 기각) | Plan | ✅ | 근본 해결. `_sync_workers` 가 이미 워커 전량 재구성이라 마이그레이션 0 으로 완결 |
| Option C — 빌더 공용 모듈 추출 (A: 중복구현 / B: 전면 리팩토링 기각) | Design §2.0 | ✅ | create -211줄, 규칙 단일화. 생성 경로 무회귀(equivalence 테스트 통과) |
| 목표 상태 전체 교체 (`None`/`[]`/`[...]`) | Design §7.2 | ✅ | `skill_ids`·`middleware_types` 와 동일 의미론으로 클라이언트 규칙 일관 |
| 기존 config 보존 머지 | Design §7.2 | ✅ | 프론트가 RAG 설정을 매번 전량 전송하지 않아도 유실 없음 |
| 종속 데이터 soft-delete | Design §7.2 | ✅ | 고아 행·유령 설정 부활 차단 |
| 빌트인 생성과 동일 규칙 재주입 | Design §7.2 | ✅ | QA R2b 로 실서버 확인 (wiki_read/wiki_list 복원) |
| MCP 동등 지원 | Design §7.2 | ✅ | 프론트가 이미 MCP 를 필터 없이 보내므로 제외 시 또 다른 조용한 무시 발생 — 방지 |
| 명시 visibility=422 vs 자동 clamp 분리 | Design §7 | ✅ | 의도적 요청은 거부, 부수적 축소는 안내 |
| **§5.1 빌트인 제외 위치 변경** | Do 중 재협의 | ⚠️ 승인된 이탈 | `mapDetailToForm` 대신 전송 시점 필터. edit 모드 칩 UI 보존 + `MAX_TOOLS` 왜곡 제거 |

---

## 2. Related Documents

| 문서 | 경로 |
|---|---|
| Plan | `docs/01-plan/features/agent-update-tool-editing.plan.md` |
| Design | `docs/02-design/features/agent-update-tool-editing.design.md` |
| Analysis | `docs/03-analysis/agent-update-tool-editing.analysis.md` |
| QA Report | `docs/05-qa/agent-update-tool-editing.qa-report.md` |

---

## 3. Completed Items

### 3.1 Functional Requirements

FR-01 ~ FR-13 **전부 구현** (상세 근거는 Analysis §2.3 의 file:line 표 참조).

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|---|---|
| 무회귀 | `tool_ids` 미전송 경로 동작 동일 — agent_builder 영향권 1056건 통과 |
| 트랜잭션 원자성 | 워커 재구성·soft-delete·저장이 단일 세션 편승 (R6) |
| 아키텍처 | domain→infrastructure 역참조 0, 빌더는 application + 인터페이스 주입 |
| 로깅 | `added_tool_ids`/`removed_tool_ids`/clamp 전후를 `request_id` 와 구조화 로깅 |
| 계약 정합 | 백엔드 스키마 ↔ 프론트 타입 3-way 6항목 일치 |

### 3.3 Deliverables

**신규 (7)**

| 파일 | 줄수 | 역할 |
|---|---|---|
| `src/application/agent_builder/worker_skeleton_builder.py` | 223 | create/update 공용 워커 빌드 |
| `tests/application/agent_builder/test_worker_skeleton_builder.py` | 258 | 빌더 단위 17건 |
| `tests/application/agent_builder/test_update_agent_tool_editing.py` | 588 | T-01~T-18 + α, 22건 |
| `tests/application/agent_builder/test_update_agent_tool_fields.py` | 62 | 스키마 계약 5건 |
| `tests/domain/agent_builder/test_replace_tool_workers.py` | 93 | 도메인 4건 |
| `idt_front/src/utils/agentToolPayload.ts` | 18 | 저장 payload tool_ids 구성 |
| `idt_front/src/utils/agentToolPayload.test.ts` | 58 | 5건 |

**수정 (7)**: `create_agent_use_case.py`(-211) / `update_agent_use_case.py`(+245) /
`application/schemas.py`(+12) / `domain/schemas.py`(+14) /
`agent_definition_repository.py`(+3) / `api/main.py`(DI) /
`idt_front` `types/agentBuilder.ts`(+12) · `AgentBuilderPage/index.tsx`(+21)

---

## 4. Incomplete Items

### 4.1 Carried Over

| 항목 | 사유 | 권고 |
|---|---|---|
| L3 브라우저 E2E | Playwright 자산 없음 | 후속 사이클에서 자산화 또는 수동 확인 |
| Analysis G-1 — MCP 미배선 전용 에러 메시지 | 설계 §6.1 문구 미구현, `Unknown tool_id` 폴백 | 메시지 보강 또는 설계 항목 삭제 |
| Analysis G-2 — 설계 §2.2 순서표 동기화 | 코드가 정책 검증을 앞으로(fail-fast) 배치 | **문서를 코드에 맞춰 갱신** |
| 독립 코드 리뷰 | gap-detector 산출 2회 실패 | 별도 리뷰어 또는 `/code-review` |

### 4.2 On Hold

| 항목 | 사유 |
|---|---|
| `blueprint_id` 존재 검증 | blueprint 는 전역 라이브러리 자원이며 실행 시점 해석 — 저장 시 검증 필요 여부는 별도 판단 |
| 수정 경로의 빌트인 opt-out 채널 | 빌트인 해제는 생성 전용 채널(builtin-tools D5) 유지가 현 계약 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 매치율 |
|---|:---:|
| Structural | 100% |
| Functional | 95% |
| API Contract | 100% |
| **Overall (정적)** | **98%** |
| Runtime (QA L1) | 6/6 PASS |

### 5.2 Resolved Issues

| # | 내용 | 발견 시점 |
|---|---|---|
| 1 | **원 결함** — `presentation_generator` 워커 부재 422 | 사용자 에러 로그 |
| 2 | 수정 경로의 모든 도구 변경이 조용히 유실 | Plan 원인 분석 중 |
| 3 | `repository.update()` 가 `flow_hint` 미저장 → 도구 변경 후 supervisor 프롬프트가 옛 도구 체인 참조 | **구현 중 발견** |
| 4 | `worker_id` 생성이 3곳 중 1곳만 `sanitize_tool_name` 경유 → MCP 콜론 ID 시 LangGraph 노드명 파손 위험 | **구현 중 발견** |
| 5 | 빌트인이 `MAX_TOOLS` 상한을 잠식 (edit 폼이 빌트인을 일반 칩으로 매핑) | **module-5 착수 중 발견** |
| 6 | clamp 결과 `department` 인데 `department_id` 부재 시 도메인 불변식 위반 조합 | 구현 중 방어 |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep

- **원인 분석을 코드 추적으로 확정한 뒤 Plan 작성**: 5단계 사슬(바인딩 → 스키마 → UseCase → 프론트 payload → UI 허용)을 file:line 으로 특정해, 증상(발표자료 422)이 아니라 진짜 범위(도구 편집 전체 부재)를 잡았다.
- **위키 선례 선참조**: `docs/wiki/frontend/screens/agent-screens.md` 의 *"수정 가능 필드 추가는 스키마+apply_update+repo update()+DI 4곳 세트 — repo 누락 시 조용히 미저장"* 을 착수 전에 읽었고, 실제로 `flow_hint` 에서 같은 함정을 발견해 즉시 처리했다.
- **행위보존 추출을 별도 모듈로 분리**: M1 을 "동작 불변 + 기존 테스트 전량 통과"로 못 박아 리팩토링 회귀와 기능 추가를 섞지 않았다.
- **TDD Red 확인**: 22건 Red → 구현 → Green 순서를 지켜 테스트가 실제로 실패를 잡는지 확인했다.

### 6.2 Problem

- **서브에이전트 산출 유실**: gap-detector 를 2회(본문 / 파일 출력) 기동했으나 모두 빈손. Check 단계의 독립 검증을 확보하지 못하고 자기검증으로 대체했다.
- **개발 서버 stale 프로세스**: `--reload` 인데도 워커가 옛 코드에 고정돼 QA 1차에서 **빌트인 소실·flow_hint 정체라는 거짓 결함**을 관측했다. 새 프로세스로 재실행해야 진위가 갈렸다.
- **워킹트리 오염**: 이번 작업과 무관한 미커밋 변경 90여 파일 때문에, 전체 스위트 실패 58건이 사전 존재인지 판별하는 데 `git stash` 대조까지 필요했다.

### 6.3 Try

- QA 착수 시 **서버 프로세스 기동 시각 vs 소스 mtime 을 먼저 대조**하는 절차를 넣는다 (이번 오진의 유일한 예방책).
- 서브에이전트에 위임할 때는 **처음부터 파일 산출을 요구**하고, 2회 실패 시 즉시 직접 수행으로 전환한다 (이번에 그렇게 했고 옳았다).
- 기능 착수 전 워킹트리 상태를 확인하고, 무관한 변경이 많으면 **베이스라인 테스트 결과를 먼저 기록**해 둔다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

- Check 단계의 gap-detector 실패에 대한 **폴백 규약**이 없다. "산출 실패 시 자기검증 + 명시적 고지" 를 스킬에 명문화하면 좋겠다.
- Design 의 순서표가 구현 중 개선(fail-fast 재배치)을 반영하지 못했다. Do 단계에서 **설계 이탈이 생기면 그 자리에서 설계 문서를 갱신**하는 규칙이 있으면 Analysis 의 G-2 같은 항목이 줄어든다.

### 7.2 도구/환경

- `uvicorn --reload` 신뢰 불가 사례가 확인됐다. 배포/검증 절차에 **명시적 재기동**을 넣어야 한다.
- 프로젝트 ruff 설정이 전체적으로 미준수 상태(437 errors)라 신규 코드 린트 신호가 묻힌다. 점진적 정리 또는 변경 파일 한정 게이트 도입을 권한다.

---

## 8. Next Steps

### 8.1 Immediate

1. **개발 서버 재기동** — 현재 8000 포트 프로세스는 이 기능의 DI·repository 변경을 들고 있지 않다.
2. 변경분 커밋/PR — 워킹트리에 무관한 변경이 많으므로 이 기능 파일만 선별 필요 (14파일).
3. Analysis G-1/G-2 정리 (에러 메시지 + 설계 문서 순서표).

### 8.2 Next Cycle

- L3 E2E 자산화 (도구 편집 왕복 시나리오).
- `/wiki update` 로 이번 선례 2건 기록: ① `flow_hint` 를 포함한 repo update 화이트리스트 함정 ② `--reload` stale 프로세스 오진 패턴.

---

## 9. Changelog

### v1.0.0 (2026-09-06)

**Added**
- `PATCH /agents/{id}` 에 `tool_ids`/`tool_configs` 도입 (목표 상태 전체 교체)
- 응답에 `visibility`/`visibility_clamped`/`max_visibility`
- `WorkerSkeletonBuilder` — create/update 공용 워커 빌드 모듈
- `AgentDefinition.replace_tool_workers()`
- 프론트 `buildToolIdsForSave` + 수정 payload 도구 전송 + clamp 안내

**Fixed**
- `presentation_generator` 워커 부재로 인한 수정 저장 422 (원 결함)
- 수정 경로 도구 변경의 조용한 유실
- `repository.update()` 의 `flow_hint` 미저장
- `worker_id` 생성 규칙 불일치 (MCP 콜론 ID 위험)
- 빌트인이 도구 상한을 잠식하는 문제

**Unchanged**
- DB 스키마 (마이그레이션 0)
- 서브에이전트 구성 계약, 빌트인 opt-out 채널 정책

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-06 | 완료 보고 — Match 98%, QA PASS, SC 7/7 | 배상규 |
