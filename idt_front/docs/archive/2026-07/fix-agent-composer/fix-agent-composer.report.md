# fix-agent-composer Completion Report

> **Feature**: Fix 에이전트 탭 — 채팅 → compose(증분 수정) → 초안 카드 → 폼 셋팅 (풀스택)
> **Period**: 2026-07-04 ~ 2026-07-05
> **Author**: 배상규
> **Status**: Completed (Match Rate 93%, iteration 0회)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | fix-agent-composer |
| 기간 | 2026-07-04 ~ 2026-07-05 (2일) |
| Match Rate | **93%** (38/41, gap-detector + 수동 검증) |
| Iteration | 0회 (1차 구현으로 90% 임계 통과) |
| 변경 파일 | 백엔드 소스 4 + 테스트 4 / 프론트 신규 9(테스트 포함) + 수정 8 / 문서 5 |
| 테스트 | 백엔드 45 passed (신규 15) / 프론트 agent-builder 141 passed (신규 37) / 전체 스위트 472 passed (신규 회귀 0) |

### 1.3 Value Delivered

| Perspective | Delivered |
|-------------|-----------|
| **Problem** | 완성돼 있던 nl-agent-composer 백엔드(compose API)에 프론트 진입점이 없어 사장돼 있었고, "기존 설정에 tavily 추가해줘" 같은 증분 수정은 API가 현재 설정을 몰라 불가능했다 |
| **Solution** | compose API를 `current_config`(폼 스냅샷)·`history`(최근 6턴, 서버 절단)로 하위호환 확장하고, Fix 에이전트 탭에 채팅 UI + 초안 카드([적용하기] 클릭 시에만 폼 반영)를 구현. MCP 도구 저장 차단 필터 3개소 제거 |
| **Function/UX Effect** | 자연어 한 줄 → 폼 자동 셋팅 + 대화를 이어가며 증분 수정. coverage 뱃지/미커버 역량/edit 제약 경고로 초안의 신뢰 수준을 투명하게 표시. MCP 도구가 선택→폼→저장까지 일관 동작 |
| **Core Value** | 에이전트 생성 진입 장벽을 "폼 작성"에서 "대화 한 줄"로 낮추고, 기존 백엔드 투자를 실제 사용자 가치로 전환. 서버 보정 파이프라인 재사용으로 안전성 유지 |

---

## 2. PDCA 이력

| Phase | 산출물 | 결과 |
|-------|--------|------|
| Plan (07-04) | `docs/01-plan/features/fix-agent-composer.plan.md` | FR-01~FR-10, 사용자 결정 4건(풀스택/초안카드/멀티턴/MCP필터제거) 반영 |
| Design (07-04) | `docs/02-design/features/fix-agent-composer.design.md` | 스키마/프롬프트 블록/컴포넌트 계약/폼 매핑표/테스트 B1~B6·F1~F11/구현 순서 Phase A~E |
| Do (07-04~05) | 아래 §3 | TDD Red→Green, Phase A~E 전부 완료 |
| Check (07-05) | `docs/03-analysis/features/fix-agent-composer.analysis.md` | **93%** — G1 오탐 기각, 잔존 갭 Low 3건 |

---

## 3. 구현 요약

### 백엔드 (idt/) — compose API 하위호환 확장
- `application/agent_composer/schemas.py`: `ComposeCurrentConfig`·`ComposeHistoryTurn` 신설, `ComposeAgentRequest`에 `current_config`/`history`(≤20턴) 추가. 응답 스키마·엔드포인트 불변
- `domain/agent_composer/policies.py`: `clamp_history` (최근 6턴·턴당 500자 서버 절단)
- `application/agent_composer/composer.py`: `[현재 에이전트 설정]`+`[증분 수정 규칙]` 블록 조건부 주입, history를 system↔user 사이 messages로 삽입
- `compose_agent_use_case.py`: 절단 후 배선 — 기존 보정 파이프라인(환각 drop/MCP 매핑/clamp/coverage 재산정) 무변경 재사용

### 프론트 (idt_front/)
- 신규: `types/agentComposer.ts`, `services/agentComposerService.ts`, `hooks/useAgentComposer.ts`, `fix/FixAgentPanel.tsx`(시안 준수 채팅), `fix/ComposeDraftCard.tsx`(초안 카드)
- 배선: `AgentTestPanel`(Fix 탭 활성화) → `StudioLayout` → `AgentBuilderPage.handleApplyDraft`(원자적 폼 반영, RAG/문서추출기 부수효과 동기화, 모델 역매핑 실패 시 유지+안내)
- MCP 필터 제거: handleSave 전송 제외 삭제, ToolPickerModal 생성 모드 차단 해제(기존 테스트 2건 신규 정책으로 갱신)
- `docs/api/nl-agent-composer.md` 확장 스펙 반영

---

## 4. 품질 검증

| 항목 | 결과 |
|------|------|
| 백엔드 pytest (composer 영역) | 45 passed — 회귀 0 |
| 프론트 vitest (agent-builder 영역) | 141 passed (신규 37) |
| 프론트 전체 스위트 | 472 passed / 8 failed — 실패는 사전 실패 기준선(collection 7+ChatPage 1)과 일치, 신규 회귀 0 |
| type-check | 통과 |
| lint | 신규 파일 0 error |
| Gap 분석 | 93% (G1은 authClient 인터셉터의 detail 변환으로 오탐 판정) |

---

## 5. 잔존 항목 (Low)

| # | 항목 | 처리 방침 |
|---|------|-----------|
| G2 | [전송↑] 버튼 미구현 (Design 다이어그램 표기) | FR 본문은 Enter 전송으로 충족 — 필요 시 후속 |
| G4 | 저장 422 → 에러 다이얼로그 테스트 미작성 | 코드는 존재(공통 onError 경로), 후속 보강 권장 |
| — | 수동 E2E (서버 기동 후 채팅→카드→적용→저장) | 배포 전 1회 권장 |
| — | edit 모드 도구 변경 저장 (Update API tool_ids 미지원) | Plan Out of Scope — 후속 feature 후보 |

---

## 6. Lessons Learned

1. **gap-detector 결과는 수동 재검증 가치가 있다** — G1(422 detail)은 authClient 응답 인터셉터(`detail→ApiError.message`)를 놓친 오탐. 레이어 간 계약은 단일 파일 분석으로 판정 불가.
2. **이 프로젝트 프론트 테스트는 파일별 `server.listen()` 수동 호출 구조** — 전역 setup에 MSW 없음. 신규 MSW 테스트 작성 시 beforeAll/afterEach/afterAll 3종 세트 필수.
3. **Windows vitest는 `--pool=threads`에 `--no-file-parallelism`까지 필요** — threads 풀도 다중 워커 기동 타임아웃 발생.
4. **하위호환 확장 패턴** — 신규 요청 필드는 전부 optional + 기본값 None, 기존 파이프라인 재사용 → 기존 테스트 무수정 통과가 하위호환의 증거가 된다.
