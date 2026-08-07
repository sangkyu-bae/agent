# agent-webhook Completion Report

> **Status**: Complete (M1 Inbound — M2 Outbound은 후속 사이클로 이월)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Completion Date**: 2026-08-07
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 단일 사이클, Act 반복 0회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-webhook — 에이전트 외부 오픈 웹훅 채널 (M1 Inbound) |
| Start Date | 2026-08-07 |
| End Date | 2026-08-07 |
| Duration | 1일 (단일 세션 Plan→Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 93.3% (48.5 / 52)              │
├─────────────────────────────────────────────┤
│  ✅ M1 기능 결손:        0건                 │
│  ✅ 보안 금지사항 검증:  4/4 통과            │
│  ✅ 테스트:  백엔드 58 + 프론트 45 통과      │
│  ⏳ 이월:  G7 E2E 수동검증 · M2 Outbound     │
│  🔄 Act 반복:  0회 (90% 임계 1차 통과)       │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행 경로가 전부 사내 JWT 전제라 완성한 에이전트를 그룹웨어·타 시스템에서 호출할 방법이 없었고, 설정 탭 Webhook 섹션은 "준비중" 스텁이었다 |
| **Solution** | 신규 1:1 테이블 `agent_webhook`(V057) 독립 opt-in + HMAC-SHA256 서명·타임스탬프(±300s) 검증 공개 엔드포인트 + 기존 RunAgentUseCase 재사용 동기 실행(소유자 AuthContext 조립) + 설정 탭 실기능 UI(키 발급 1회 노출·재발급·토글·삭제) |
| **Function/UX Effect** | P2(소유자)가 설정 탭에서 토글·버튼만으로 에이전트를 외부 호출 가능한 API로 오픈 — 관리 API 5본 + 공개 inbound 1본, 신규 코드 계층 7개(신규 파일 백엔드 15·프론트 6), 기존 실행 파이프라인·관측(ai_run) 무수정 재사용으로 기존 코드 수정은 main.py 배선 + 프론트 4파일뿐 |
| **Core Value** | 에이전트가 플랫폼 UI 안의 도구에서 그룹 시스템에 끼워 넣을 수 있는 서비스 컴포넌트로 승격 — 외부 연동 첫 관문을 표준 웹훅 보안(서명·재생 방어·키 회전)으로 확보, Match Rate 93.3%·회귀 0 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | `docs/01-plan/features/agent-webhook.plan.md` | ✅ Finalized |
| Design | `docs/02-design/features/agent-webhook.design.md` | ✅ Finalized (정정 3건 §5.2 참조) |
| Check | `docs/03-analysis/agent-webhook.analysis.md` | ✅ Complete (93.3%) |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan §3.1 M1 — FR-01~09)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 활성화 시 시크릿 발급, 평문 1회 노출 | ✅ | 응답 스키마 분리로 구조적 강제 (`WebhookConfigResponse`에 secret 필드 부재) |
| FR-02 | HMAC-SHA256 + 타임스탬프 ±300s 검증, 실패 401 | ✅ | 상수시간 비교, 경계(±299/±301) 테스트 |
| FR-03 | 미설정·비활성 호출 404 (존재 비노출) | ✅ | 4가지 실패 원인 단일 문구 |
| FR-04 | 소유자 신원 동기 실행, RunAgentResponse 동형 반환 | ✅ | AssembleAuthContextUseCase로 owner ctx 조립 |
| FR-05 | rotate 시 구키 즉시 무효 | ✅ | 구서명 검증 실패 테스트 단언 |
| FR-06 | 관리 API 소유자 전용 (타인 403) | ✅ | `ensure_owned_agent` (agent_schedule 동형) |
| FR-07 | 설정 탭 토글·발급/재발급/복사·URL 확인 | ✅ | WebhookSection — create 모드는 안내문(D9) |
| FR-08 | 웹훅 실행 ai_run 관측 기록 | ✅* | 기존 파이프라인 재사용으로 구조상 충족 — 실측은 G7 E2E에서 확인 |
| FR-09 | 기존 실행 경로·설정 탭 무회귀 | ✅ | 빌더 페이지·스튜디오 회귀 24건 통과 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 시크릿 보호 | 로그·조회 응답 미노출 | 로그 인자 0건·응답 스키마 분리 (분석 §8) | ✅ |
| 레이어 준수 | domain=stdlib만 / infra / interfaces 분리 | policies.py는 hmac·hashlib·secrets만 | ✅ |
| DDL 규칙 | 전 컬럼 COMMENT·FK CHARSET 금지 | `test_migration_ddl_comments.py` 통과 | ✅ |
| TDD | 테스트 선행 | 백엔드 58 + 프론트 45 (신규 66) | ✅ |
| API 계약 동기화 | api.ts·types·service·hook 동반 | 6개 파일 신설/수정 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `db/migration/V057__create_agent_webhook.sql` | ✅ (배포 전 적용 필수) |
| domain | `src/domain/agent_webhook/` (entity·policies·interfaces) | ✅ |
| infrastructure | `src/infrastructure/agent_webhook/` (models·repository) | ✅ |
| application | `src/application/agent_webhook/` (schemas·access·관리 5종·invoke) | ✅ |
| interfaces | `agent_webhook_router.py`(5본) + `webhook_public_router.py`(1본) + main.py DI | ✅ |
| 프론트 | `WebhookSection.tsx` + service/hook/types/constants/queryKeys + SettingsPanel·AgentTestPanel 배선 | ✅ |
| 테스트 | tests/{domain,application,api} 4파일 + WebhookSection.test + SettingsPanel.test 갱신 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| **G7: E2E 수동 검증** (V057 적용 → 활성화 → curl 서명 호출 → ai_run 관측 → rotate 후 구키 401) | 로컬 DB에 V057 미적용 상태 — 배포 전 체크리스트 | High | 0.5h |
| **M2: Outbound** (V058 delivery 로그·발송+재시도 3회·스케줄/웹훅 실행 훅·설정 UI) | Plan 확정 마일스톤 분리 — Design §9에 설계 확정본 존재 | High | 1 사이클 |
| 커밋/PR | 사용자 지시 대기 | — | — |
| Rate limiting / 호출 쿼터 | Plan Out of Scope 명시 (공개 표면의 수용 리스크) | Medium | 별도 사이클 |

### 4.2 Cancelled/On Hold Items

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Note |
|--------|--------|-------|------|
| Design Match Rate | ≥ 90% | **93.3%** | 1차 통과, Act 반복 0회 |
| M1 기능 결손 | 0 | 0 | 미구현 항목 없음 |
| 보안 금지사항 | 4/4 | 4/4 | 분석 §8 전항 통과 |
| 신규 테스트 | 설계 §6 전 케이스 | 66건 (백 58 중 신규 48 + 프론트 신규 8 + 갱신 13중 신규 2) 통과 | tsc 클린 |

### 5.2 Resolved Issues (구현 중 발견·해결)

| Issue | Resolution | Result |
|-------|------------|--------|
| **설계 모순: 시크릿 해시 저장 ↔ HMAC 재계산 불가** | Design 단계에서 발견, D2를 평문 저장으로 정정 (MCP api_key 선례 수준) — Plan의 "해시 저장" 가정 폐기 | ✅ 설계 단계 조기 해소 |
| DDL comment 검사기가 COMMENT 문자열 내 최상위 콤마를 컬럼 구분자로 오인 | COMMENT 문구에서 콤마 제거 (검사기는 따옴표 비인식 — 관례로 회피) | ✅ |
| jsdom `navigator.clipboard` 읽기 전용으로 Object.assign 스텁 실패 | userEvent.setup() 내장 클립보드 스텁 + `readText()` 검증으로 전환 | ✅ |
| Design 문서 잔재 (G2 `hash()`·G3 repo 경로·G6 prop 타입) | 코드가 정답 — 본 보고서에 정정 기록 (문서 수정은 아카이브 시점 불필요 판단) | ✅ 기록 종결 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **선례 재사용이 회귀 반경을 0으로 만듦**: 스케줄 트리거의 "무요청 실행 + `_build_run_agent_uc` 공유" 선례를 invoke에 그대로 적용 — 실행 파이프라인·관측 코드 무수정.
- **질문 선행(AskUserQuestion 4문)이 설계 방향을 1회에 고정**: Inbound/Outbound·인증·동기/비동기·범위를 Plan 전에 확정해 방향 재작업 0.
- **응답 스키마 분리로 보안 규칙을 구조화**: "시크릿 1회 노출"을 코드 리뷰 규칙이 아니라 `WebhookSecretResponse`/`WebhookConfigResponse` 타입 분리로 강제.

### 6.2 What Needs Improvement (Problem)

- **Plan 단계의 암호학 가정 오류**: "해시 저장"은 HMAC과 양립 불가 — 인증 스킴을 정할 때 저장 방식까지 같이 검증했어야 함. Design에서 잡았지만 Plan 리스크 표에 오르지 못했음.
- **vitest 워커 기동 불안정**: threads 풀에서도 간헐 타임아웃 — 재시도로 해소했으나 대규모 테스트 실행 비용이 큼(백그라운드 실행 필수).

### 6.3 What to Try Next (Try)

- M2 Outbound에서 409/404 분기를 메시지 문자열 매칭 대신 전용 예외로 승격 (G5).
- 공개 엔드포인트 rate limit 사이클 기획 (인프라 레벨 vs 앱 레벨 결정 포함).

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 보안 스킴과 저장 방식을 분리 기술 | 인증/암호 관련 결정은 "검증 시 서버가 무엇을 알아야 하는가"를 Plan 체크 항목화 |
| Check | E2E 수동 검증이 반복 이월됨 (프로젝트 공통 패턴) | Qdrant/ES/MySQL 기동 시 이월 E2E 일괄 소화하는 정기 체크리스트 운영 (kb-pipeline-e2e-pending과 병합) |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] `git-workflow`로 feature 브랜치 커밋 + PR (사용자 지시 시)
- [ ] 배포 전: **V057 적용** → G7 E2E 체크리스트 수행
- [ ] 외부 시스템 안내용 서명 생성 가이드 공유 (Design §4-4 curl 예시)

### 8.2 Next PDCA Cycle

| Item | Priority | 비고 |
|------|----------|------|
| agent-webhook-outbound (M2) | High | Design §9 확정본 존재 — V058·발송·재시도·이력 UI |
| webhook rate limiting | Medium | 공개 표면 보호 |

---

## 9. Changelog

### M1 (2026-08-07)

**Added:**
- V057 `agent_webhook` 테이블 (1:1 opt-in, outbound 컬럼 선포함)
- 관리 API 5본 (`POST/GET/PATCH/DELETE /api/v1/agents/{id}/webhook`, `POST …/rotate`)
- 공개 inbound `POST /api/v1/webhooks/agents/{id}` (HMAC-SHA256 + 타임스탬프 검증, JWT 없음)
- `WebhookSecretPolicy`·`WebhookSignaturePolicy` (domain, stdlib 전용)
- 설정 탭 WebhookSection 실기능 (시크릿 1회 모달·복사·토글·재발급·삭제·소유자 경고)

**Changed:**
- SettingsPanel: Webhook 스텁("Bearer dbuilder_xxx" 안내) → 실기능 섹션 + `agentId` prop
- constants/api.ts·queryKeys.ts: 웹훅 상수·쿼리키 추가

**Fixed:**
- 해당 없음 (신규 기능)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-07 | Completion report created | 배상규 |
