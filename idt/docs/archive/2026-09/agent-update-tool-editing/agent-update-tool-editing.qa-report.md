# Agent Update Tool Editing QA Report

> **Project**: sangplusbot (idt)
> **Date**: 2026-09-06
> **Tester**: 배상규
> **Design Doc**: [agent-update-tool-editing.design.md](../02-design/features/agent-update-tool-editing.design.md)
> **Analysis Doc**: [agent-update-tool-editing.analysis.md](../03-analysis/agent-update-tool-editing.analysis.md)
> **결과**: **QA_PASS** (L1 6/6, L2 프론트 11/11, L3 미실행)

---

## 1. 테스트 환경

| 항목 | 값 |
|---|---|
| 백엔드 | 임시 인스턴스 `127.0.0.1:8010` (QA 전용, 검증 후 종료) |
| 인프라 | 기존 dev 컨테이너 재사용 (basic-mysql-1, qdrant, elasticsearch, redis — 모두 Up) |
| 계정 | `testuser@sangplus.dev` (`scripts/seed_test_users.sql`, 로컬 전용 시드) |
| 테스트 데이터 | 임시 에이전트 `QA-tool-editing-temp` 생성 → 검증 후 **DELETE 204 로 정리 완료** |

### 사용자 서버(8000)를 쓰지 않은 이유 — 중요 발견

기동 중이던 사용자 서버(`--reload`, PID 34036)의 워커 자식 프로세스가 **16:08:47 시점 코드에 고정**돼
있었다. `src/api/main.py`(16:18:59)·`agent_definition_repository.py`(16:11:38) 수정 후에도
리로드가 발생하지 않았고, 파일 `touch` 로도 재기동되지 않았다.

이 상태에서 1차 실행한 R1/R2 는 **빌트인 워커 소실**과 **`flow_hint` 정체**를 보였는데,
동일 시나리오를 **새 프로세스**에서 재실행하자 둘 다 정상이었다.
→ 코드 결함이 아니라 **stale 프로세스 아티팩트**로 확정. 사용자 서버는 건드리지 않고
별도 포트에 임시 인스턴스를 띄워 검증했다.

> **운영 시사점**: 이 기능을 dev 서버에 반영하려면 `--reload` 를 신뢰하지 말고
> **uvicorn 프로세스를 명시적으로 재기동**해야 한다. main.py(DI)·infrastructure 변경이
> 조용히 미반영되면 빌트인 소실처럼 "결함처럼 보이는" 증상이 나온다.

---

## 2. L1 — API 런타임 시나리오

| ID | 시나리오 | 기대 | 실제 | 결과 |
|---|---|---|---|:---:|
| R0 | OpenAPI 스키마 노출 | `tool_ids`/`tool_configs` + `visibility`/`visibility_clamped`/`max_visibility` | 전부 노출 확인 | ✅ |
| R1 | **발표자료생성기 추가 + 양식 설정 저장** (원 결함 경로) | 200 | **200** | ✅ |
| R2 | 상세 조회 — 워커·설정 영속 | presentation_generator 워커 + tool_config | `presentation_generator_worker` / `blueprint_id=qa-blueprint-placeholder`, `max_slides=12`, `output_format=pptx` | ✅ |
| R2b | 빌트인 재주입 (FR-09) | wiki_read/wiki_list 유지 | `['tavily_search','presentation_generator','wiki_read','wiki_list']` sort 0~3 | ✅ |
| R2c | `flow_hint` 갱신 (구현 중 발견 결함) | `tavily_search → presentation_generator` | 일치 | ✅ |
| R3 | 도구 제거 (SC-2) | 워커 소멸 | `['tavily_search','wiki_read','wiki_list']` | ✅ |
| R4 | `tool_configs` 단독 전송 | 422 + 안내 메시지 | `422 {"detail":"tool_configs 는 tool_ids 와 함께 전달해야 합니다."}` | ✅ |
| R5 | `tool_ids` 미전송 (SC-5 무회귀) | 도구 구성 무변경 | 변경 없음 | ✅ |

**L1: 6/6 PASS** (R2b/R2c 포함 8개 관측 항목 전부 일치)

### 원 결함 재현 대조

| | 수정 전 (사용자 로그 2026-09-05T10:03:39Z) | 수정 후 (R1) |
|---|---|---|
| 응답 | `ValueError: presentation_generator 도구 워커가 없어…` → 422 | **HTTP 200** |
| 워커 | 생성 안 됨 | `presentation_generator_worker` 생성 + config 주입 |

---

## 3. L2 — 프론트 단위/통합 (Vitest + MSW)

| 파일 | 건수 | 결과 |
|---|---|:---:|
| `src/utils/agentToolPayload.test.ts` | 5 | ✅ |
| `src/pages/AgentBuilderPage/index.test.tsx` (도구 편집 6건 포함 총 22건) | 6 신규 | ✅ |

F-01(카탈로그 표기 전송) / F-01b(빈 배열) / F-02(tool_configs 키) / F-03(빌트인 제외) /
F-04·F-04b(clamp 안내) 전부 통과.

---

## 4. L3 — E2E

**미실행.** 이 기능은 Playwright 자산이 없고, 프론트 개발 서버 + 브라우저 왕복이 필요하다.
L1 이 API 왕복(저장→영속→재조회)을, L2 가 페이로드 생성·응답 소비를 각각 덮으므로
잔여 리스크는 **브라우저 UI 조작 경로**(도구 칩 토글 → 저장 버튼)에 한정된다.

---

## 5. L4/L5 (성능/보안)

프로젝트 레벨상 필수 아님. 단 보안 관련 1건은 L1 에서 간접 확인:
`visibility` scope 재검증이 요청마다 수행되며(`_apply_scope_clamp`), 도구 변경으로
공개 범위를 넓히는 우회 경로는 없다.

---

## 6. 잔여 이슈

| # | 심각도 | 내용 | 조치 |
|---|---|---|---|
| Q-1 | Info | `blueprint_id` 는 존재 검증 없이 저장됨 (`qa-blueprint-placeholder` 가 그대로 통과) | 설계상 blueprint 는 전역 라이브러리 자원이며 실행 시점에 해석됨. 저장 시 존재 검증이 필요한지는 별도 판단 사안 |
| Q-2 | Info | L3 브라우저 경로 미검증 | 수동 확인 또는 후속 E2E 자산화 |
| Q-3 | Minor | Analysis G-1(MCP 미배선 전용 메시지)·G-2(설계 순서표 동기화) 미해소 | 문서/메시지 사안 — 별도 처리 |

---

## 7. 판정

**QA_PASS** — 원 결함 경로가 실서버에서 200 으로 복구됐고, 설계 §4.2 의미론 5행 중
런타임 검증 가능한 4행(무변경/422/추가/제거)이 실제 응답으로 확인됐다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-06 | L1 6/6 · L2 11/11 PASS. stale 서버 프로세스 이슈 기록 | 배상규 |
