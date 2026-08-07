# Agent Webhook Outbound (M2) Planning Document

> **Summary**: agent-webhook M1(Inbound)의 확정 후속 마일스톤 — 에이전트 실행(스케줄 트리거·inbound 웹훅) 완료 시 소유자가 등록한 외부 URL로 **서명된 결과 payload를 POST 발송**하고, 실패 재시도(3회 지수 백오프)·전송 이력(V058)을 제공한다. M1이 선포함해 둔 `agent_webhook.outbound_url/outbound_enabled` 컬럼과 `WebhookSignaturePolicy.sign()`을 그대로 재사용 — 아카이브된 Design §9 확정 개요의 정식화
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft
> **선행**: agent-webhook M1 (2026-08-07 아카이브, 93.3%) — 워킹트리 미커밋 상태이므로 **M1 커밋 후 착수 권장**

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | M1으로 외부→에이전트 호출(Inbound)은 열렸지만 반대 방향이 없다 — 스케줄 실행 결과가 플랫폼 안에만 남아 소유자가 매번 들어와 확인해야 하고, 그룹웨어·사내 알림 시스템으로 결과를 흘려보낼 수 없다. `agent_webhook.outbound_url` 컬럼은 V057에 예약만 된 상태 |
| **Solution** | ① 스케줄 트리거·inbound 웹훅 실행 **완료 직후 훅 2곳**에서 등록 URL로 결과 payload POST(동일 시크릿 HMAC 서명 — 수신측 검증 가능) ② 실패 시 3회 지수 백오프 재시도, 발송 실패는 실행 결과에 불영향(오류 격리) ③ V058 `agent_webhook_delivery` 전송 이력 + 조회 API ④ 설정 탭 Webhook 섹션에 outbound URL 등록·토글·최근 이력 표시 |
| **Function/UX Effect** | 소유자가 URL 하나 등록하면 "아침 9시 스케줄 요약이 사내 수신 엔드포인트로 자동 도착"하는 push 채널 완성. 발송 실패도 이력 화면에서 상태코드·오류로 즉시 진단 가능 |
| **Core Value** | 웹훅 채널의 양방향 완성(호출+발송) — 에이전트가 사람이 열어봐야 하는 도구에서 **사내 시스템에 결과를 밀어 넣는 자동화 컴포넌트**로 확장. M1 자산(테이블 컬럼·서명 정책·설정 UI) 재사용으로 신규 표면 최소 |

---

## 1. Overview

### 1.1 Purpose

`outbound_enabled`인 에이전트의 실행이 완료되면, 등록된 `outbound_url`로 서명된 결과를 POST 발송한다.
발송 계기는 **스케줄 트리거 실행**과 **inbound 웹훅 실행** 2종이며(사내 UI 수동 실행은 제외 — 노이즈 방지,
M1 Design 확정), 발송은 실행의 부수 효과로 격리되어 실패해도 실행 자체를 실패시키지 않는다.

### 1.2 Background (M1 산출물 — 재사용 자산)

| 자산 | 위치 | M2에서의 역할 |
|------|------|--------------|
| `agent_webhook.outbound_url`(NULL)·`outbound_enabled`(FALSE) | V057 선포함 | **ALTER 불필요** — 값 채우는 코드만 작성 |
| `WebhookSignaturePolicy.sign(secret, ts, raw_body)` | `src/domain/agent_webhook/policies.py` | 발송 payload 서명에 그대로 재사용 (수신측이 M1과 동일 방식 검증) |
| `UpdateWebhookRequest` / `UpdateWebhookUseCase` | `application/agent_webhook/` | outbound 필드 확장 지점 (Design 명시 예약) |
| `WebhookConfigResponse.outbound_url/outbound_enabled` | 이미 응답에 포함 | 프론트는 값 표시만 추가 |
| 스케줄 실행 분기점 `_run_one` 성공 경로 | `trigger_due_schedules_use_case.py:95-126` | 발송 훅 ① |
| `InvokeWebhookAgentUseCase.execute` 완료 지점 | `invoke_webhook_agent_use_case.py` | 발송 훅 ② |
| WebhookSection (설정 탭) | `settings/WebhookSection.tsx` | outbound UI 추가 지점 |
| 확정 설계 개요 | 아카이브 `docs/archive/2026-08/agent-webhook/agent-webhook.design.md` §9 | V058 DDL·payload·sender 스펙 초안 |

**M1 이월 교훈 반영**: 409/404 분기의 문자열 매칭(G5)을 M2 신규 코드에서는 전용 예외로 설계한다.

### 1.3 Related Documents

- M1 전체: `docs/archive/2026-08/agent-webhook/` (plan/design/analysis/report)
- 스케줄 실행 구조: `docs/archive/2026-07(38)/agent-schedule` 계열 + `trigger_due_schedules_use_case.py` 주석
- optional 의존성 무회귀 패턴 선례: agent-memory (Phase 1 — 미주입 시 무동작)
- 로깅/DB 세션 규칙: `docs/rules/logging.md`, `docs/rules/db-session.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. DB — V058 `agent_webhook_delivery`**: 발송 이력 (agent_id FK, run_id, url 스냅샷,
      trigger_source(schedule|webhook), success, status_code, attempts, error, duration_ms, created_at)
      — 테이블+전 컬럼 COMMENT(문구 내 최상위 콤마 금지 — M1 함정), FK CHARSET/COLLATE 금지, SQLAlchemy 모델 동반.
- [ ] **S2. 도메인 — `WebhookOutboundPolicy`**: URL 검증(http/https 스킴만, 형식 검증) +
      재시도 정책 상수(MAX_ATTEMPTS 3, 백오프 1/2/4s, 요청 타임아웃 10s) + payload 스키마 규칙.
- [ ] **S3. 발송기 — `infrastructure/webhook/outbound_sender.py`**: httpx.AsyncClient 기반 POST,
      D1 서명 헤더 부착(`X-Webhook-Timestamp`/`X-Webhook-Signature` — sign() 재사용), 재시도 후
      시도 결과(status_code·attempts·error·duration_ms) 반환. 시크릿·payload 본문 로그 미전달.
- [ ] **S4. 발송 유스케이스 + 훅 배선**: `DispatchOutboundWebhookUseCase` —
      outbound_enabled 확인 → payload 조립(`event: agent.run.completed`, agent_id, run_id, session_id,
      answer, tools_used, triggered_by, timestamp) → 발송 → delivery 기록.
      훅 ① `TriggerDueSchedulesUseCase`(optional 의존성 주입 — 미주입 시 무동작, 하위호환),
      훅 ② `InvokeWebhookAgentUseCase`(동일). 발송 예외는 try/except 격리 + 로그 (FR-13 계승).
- [ ] **S5. 관리 API 확장**: `PATCH /{agent_id}/webhook` body에 `outbound_url`(null=해제)·`outbound_enabled`
      optional 추가(URL 검증 422) + `GET /{agent_id}/webhook/deliveries?limit=20` 신설 (소유자 전용).
- [ ] **S6. 프론트 — WebhookSection outbound 하위 섹션**: URL 입력+저장, outbound 토글,
      최근 전송 이력 목록(시각·trigger_source·상태코드·성공 배지). types/service/hook 확장.
- [ ] **S7. 테스트 (TDD)**: 도메인 URL/재시도 정책 단위 · sender 재시도/타임아웃(HTTP mock) ·
      dispatch 유스케이스(비활성 무발송·실패 격리·이력 기록) · 훅 배선(스케줄/invoke 완료 시 호출,
      미주입 무동작) · 라우터(PATCH 검증 422·deliveries 200/403) · 프론트(입력·토글·이력 렌더).

### 2.2 Out of Scope

- 수동(사내 UI) 실행 결과 발송 — M1 Design 확정 제외 (노이즈 방지)
- 발송 큐/브로커 (비동기 워커·Redis 등) — 실행 프로세스 내 재시도로 충분, 규모 확인 후 후속
- delivery 이력 보존 기한/정리 배치 — 후속 (운영 데이터 축적 후)
- 내부 IP 대역 차단 (SSRF) — 사내망 수신이 정상 유스케이스, http/https 스킴 제한만 (M1 리스크 결정 유지)
- 실패 시 소유자 알림(메일 등) — 이력 화면 확인으로 1차 충분
- rate limiting (M1 이월 그대로 별도 사이클)

---

## 3. Requirements

### 3.1 Functional Requirements (M1 Plan FR-10~14 승계 + 세분화)

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-10 | 소유자가 outbound URL(http/https만)을 등록·수정·해제(null)하고 outbound_enabled를 토글할 수 있다 — 잘못된 URL은 422 | High | Pending |
| FR-11 | 스케줄 트리거·inbound 웹훅 실행 **성공** 완료 시 outbound_enabled면 서명된 payload가 등록 URL로 POST된다 (수동 UI 실행은 발송 없음) | High | Pending |
| FR-12 | 발송 실패 시 최대 3회 지수 백오프(1/2/4s) 재시도하고, 최종 결과(성공/실패·상태코드·시도 횟수·오류)가 delivery 이력에 기록된다 | High | Pending |
| FR-13 | 발송 실패·예외가 에이전트 실행 결과와 스케줄 이력(success)을 오염시키지 않는다 (완전 격리) | High | Pending |
| FR-14 | 설정 탭에서 outbound URL 등록·토글·최근 전송 이력(20건)을 확인할 수 있다 | High | Pending |
| FR-15 | payload 서명은 inbound와 동일 스킴(HMAC-SHA256, `{ts}.{body}`)으로 수신측이 동일 코드로 검증 가능하다 | High | Pending |
| FR-16 | 발송 훅은 optional 의존성 — 미주입 환경(기존 테스트·스크립트)에서 무동작으로 하위호환 | High | Pending |
| FR-17 | 기존 M1 동작(inbound 검증·관리 API·설정 UI) 무회귀 — PATCH의 enabled 단독 요청은 기존과 동일 동작 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 오류 격리 | 발송 경로의 어떤 예외도 실행 트랜잭션·응답에 미전파 | 격리 테스트 (sender 예외 주입) |
| 보안 | 시크릿·payload 본문 로그 미전달, URL 스킴 제한 | 코드 리뷰 + 단위 테스트 |
| DDL | V058 COMMENT 규칙 (콤마 함정 포함), FK CHARSET 금지 | `test_migration_ddl_comments.py` |
| 계약 확장 | PATCH 확장은 additive optional — M1 프론트/테스트 무수정 통과 | 기존 테스트 무회귀 |
| 세션 규칙 | delivery 기록은 실행 세션과 분리(발송은 실행 완료 후) — repo 내 commit 금지 | 코드 리뷰 |
| TDD | 테스트 선행, vitest `--pool=threads`(워커 기동 재시도 감안), MSW per-file listen | 신규 테스트 동반 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 로컬 수신 서버(테스트용)에 URL 등록 → 스케줄 트리거 실행 → 서명된 payload 도착 + M1 검증 코드로 서명 재현 (E2E 수동)
- [ ] inbound 웹훅 호출 완료 시에도 동일 발송 (E2E 수동)
- [ ] 수신 서버 다운 상태에서 3회 재시도 후 실패 이력 기록 + 스케줄 이력은 success 유지 (테스트 단언)
- [ ] 설정 탭에서 URL 등록→토글→이력 확인 왕복
- [ ] `ftp://` 등 비허용 스킴 422 (테스트 단언)
- [ ] M1 테스트 전량 + 기존 스위트 무회귀

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·중첩 2단계·config 하드코딩 금지 (재시도/타임아웃은 정책 상수)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 동기 발송(재시도 포함 최대 ~17s)이 inbound 응답·스케줄 회차 처리를 지연 | Medium | Medium | inbound: 응답 반환 **후** 발송할지(fire-and-forget task) 응답 전 발송할지 Design 확정 — 기본안은 스케줄=인라인(배치 특성상 지연 무해), inbound=`asyncio.create_task` 비차단. 태스크 예외 격리 필수 |
| 발송 실패 격리 누락 → 스케줄 이력 오염 | High | Low | 훅 지점 try/except + 격리 테스트 선행 (FR-13) |
| outbound URL 오등록(오타)으로 조용한 실패 | Medium | Medium | delivery 이력 UI로 표면화 + 등록 시 URL 형식 검증. 테스트 발송 버튼은 후속 후보 |
| M1 미커밋 위에 M2 누적 → diff 비대·리뷰 곤란 | Medium | High | **M1 커밋/PR 선행 권장** (§선행 조건). 최소한 커밋 분리 |
| httpx 신규 의존? | Low | Low | 이미 프로젝트 의존성에 존재(LangChain 계열 하위 의존) — Design에서 버전 확인만 |
| 이력 테이블 무한 증가 | Low | Low | limit 조회만 제공, 정리 배치는 Out of Scope 명시 (후속) |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Enterprise | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 발송 시점 | 모든 실행 / 스케줄만 / **스케줄+inbound** | 스케줄+inbound (M1 Design 확정 승계) | "외부 연동 채널의 실행"에 한정 — UI 수동 실행 발송은 노이즈 |
| 발송 방식 | 인라인 동기 / 백그라운드 태스크 / 큐 | **스케줄=인라인, inbound=비차단 태스크 (Design 확정)** | 배치는 지연 무해, inbound는 호출자 응답 지연 방지. 큐는 YAGNI |
| 재시도 | 없음 / 프로세스 내 3회 백오프 / 큐 기반 | **프로세스 내 3회 (1/2/4s)** | M1 Design 확정. 규모 확인 전 브로커 도입 안 함 |
| 이력 저장 | 없음 / 로그만 / **V058 테이블** | V058 테이블 | 외부 발송은 실패 진단 수단 필수 — UI 노출까지 연결 |
| 훅 주입 | 필수 의존성 / **optional 의존성** | optional (미주입 무동작) | agent-memory 무회귀 패턴 — 기존 테스트·DI 하위호환 |
| 에러 계약 | 문자열 매칭 / **전용 예외** | M2 신규 코드는 전용 예외 | M1 G5 교훈 반영 (기존 M1 코드 소급은 Design에서 판단) |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── db/migration/V058__create_agent_webhook_delivery.sql   # S1
├── src/
│   ├── domain/agent_webhook/
│   │   ├── policies.py                  # S2: WebhookOutboundPolicy 추가
│   │   ├── entity.py                    # S1: WebhookDelivery 엔티티 추가
│   │   └── interfaces.py                # delivery repo 인터페이스 추가
│   ├── infrastructure/
│   │   ├── agent_webhook/models.py      # S1: AgentWebhookDeliveryModel
│   │   ├── agent_webhook/repository.py  # delivery repo (또는 분리 파일)
│   │   └── webhook/outbound_sender.py   # S3: 신설 (httpx)
│   ├── application/
│   │   ├── agent_webhook/
│   │   │   ├── schemas.py               # S5: PATCH 확장 + Delivery 응답
│   │   │   ├── manage_webhook_use_cases.py  # S5: Update 확장 + ListDeliveries
│   │   │   ├── dispatch_outbound_use_case.py  # S4: 신설
│   │   │   └── invoke_webhook_agent_use_case.py  # S4: 훅 ② (optional 주입)
│   │   └── agent_schedule/trigger_due_schedules_use_case.py  # S4: 훅 ① (optional 주입)
│   └── api/
│       ├── routes/agent_webhook_router.py   # S5: deliveries GET
│       └── main.py                          # DI 확장
└── tests/ (domain·application·api 대응)      # S7

idt_front/src/
├── types/agentWebhook.ts                # outbound·delivery 타입
├── services/agentWebhookService.ts      # update 확장 + listDeliveries
├── hooks/useAgentWebhook.ts             # useWebhookDeliveries + update 확장
└── components/agent-builder/settings/
    └── WebhookSection.tsx (+test)       # S6: outbound 하위 섹션
```

> payload 필드 상세·inbound 비차단 태스크의 수명 관리(테스트 가능성)·delivery repo 분리 여부는 Design 확정.

---

## 7. Convention Prerequisites

- [x] M1 자산 확인 완료 (V057 컬럼·sign() 재사용·확장 지점) — §1.2
- [x] DDL COMMENT 콤마 함정·FK CHARSET 금지·jsdom clipboard·vitest threads 등 M1 함정 목록 승계
- [x] optional 의존성 무회귀 패턴 (agent-memory 선례)
- [ ] Design 확정 항목: payload 스키마 상세, inbound 발송 비차단 방식(create_task vs 응답 전 인라인), delivery repo 구조, M1 G5 예외 소급 여부, httpx 버전 확인
- [ ] **M1 커밋/PR 선행 권장** — 미커밋 누적 diff 방지
