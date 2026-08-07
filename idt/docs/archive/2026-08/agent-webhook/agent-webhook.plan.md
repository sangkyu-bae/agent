# Agent Webhook Planning Document

> **Summary**: 완성한 에이전트를 외부 시스템에 오픈하는 **웹훅 채널** — ① Inbound: 에이전트별 시크릿 키+HMAC 서명으로 인증되는 공개 엔드포인트로 외부 시스템이 에이전트를 동기 실행(M1), ② Outbound: 실행 완료 결과를 소유자가 등록한 외부 URL로 서명 POST 발송(M2). 빌더 설정 탭의 기존 Webhook 스텁(agent-settings-tab에서 자리 예약)을 실기능으로 전환하는 풀스택 사이클
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행 경로가 전부 사내 JWT 로그인 전제(`POST /api/v1/agents/{agent_id}/run`, agent_builder_router.py:270)라서, 완성한 에이전트를 그룹웨어·타 시스템 등 **외부에서 호출할 방법이 없다**. 스케줄 실행 결과도 플랫폼 안에만 남아 외부 채널로 흘려보낼 수 없다. 설정 탭의 Webhook 섹션은 "준비중" 스텁으로만 존재 |
| **Solution** | ① 에이전트별 opt-in 웹훅 채널 신설(신규 테이블 `agent_webhook`, 기존 스키마 무변경) — 시크릿 키 발급(해시 저장·평문 1회 노출)·재발급·비활성화 ② JWT를 우회하는 공개 inbound 엔드포인트 + **HMAC-SHA256 서명·타임스탬프 검증** 후 기존 run_agent 파이프라인으로 동기 실행 ③ (M2) 실행 완료 시 등록된 외부 URL로 서명된 결과 payload POST + 재시도 + 전송 로그 ④ 설정 탭 Webhook 섹션 실기능화(활성 토글·키 관리·URL 등록) |
| **Function/UX Effect** | P2(에이전트 소유자)가 빌더 설정 탭에서 토글 하나로 자기 에이전트를 "외부에서 호출 가능한 API"로 오픈하고, 발급받은 URL+키를 외부 시스템에 전달하면 즉시 연동된다. 스케줄/웹훅 실행 결과는 사내 시스템·메신저 수신 엔드포인트로 자동 발송 가능 |
| **Core Value** | 에이전트가 플랫폼 UI 안에 갇힌 도구에서 **그룹 시스템 전반에 끼워 넣을 수 있는 서비스 컴포넌트**로 승격 — Agent Builder 플랫폼 비전(일반화 우선)의 외부 연동 첫 관문. 기존 실행·관측(ai_run) 파이프라인을 그대로 재사용해 회귀 반경 최소화 |

---

## 1. Overview

### 1.1 Purpose

특정 에이전트를 소유자가 명시적으로 opt-in 하면:

- **Inbound (M1)**: 외부 시스템이 공개 URL로 POST → 서명 검증 → 해당 에이전트 동기 실행 → 결과 JSON 응답.
- **Outbound (M2)**: 에이전트 실행(스케줄 트리거·inbound 웹훅 실행) 완료 시 소유자가 등록한
  외부 URL로 서명된 결과 payload를 POST 발송.

### 1.2 Background (2026-08-07 코드 조사로 확정)

**현재 실행 경로 (전부 사내 JWT 전제)**:

| 구간 | 위치 | 상태 |
|------|------|------|
| 동기 실행 API | `POST /api/v1/agents/{agent_id}/run` — `get_current_user` 의존 | 기존재 (재사용 대상) |
| 실행 계약 | `RunAgentRequest(query≤2000, user_id, session_id?, attachments?)` → `RunAgentResponse(answer, tools_used, request_id, session_id, run_id)` (application/agent_builder/schemas.py:163-179) | 기존재 |
| SSE 스트리밍 | `GET /{agent_id}/run/stream` | 기존재 (외부 노출 안 함) |
| 스케줄 실행 | `agent_schedule_router` + 트리거 — outbound 발송 훅 후보 지점 | 기존재 |
| 관측 | `ai_run` 계열 (run_id 반환) — 웹훅 실행도 동일 기록 경로 태움 | 기존재 |
| 외부 자격증명 | **없음** — JWT 외 인증 수단 부재 | 신설 필요 |
| 설정 탭 Webhook UI | `SettingsPanel.tsx` 내 disabled+"준비중" 스텁 (agent-settings-tab 사이클에서 자리 예약) | 실기능 전환 대상 |
| 마이그레이션 | 최신 V056 (`middleware_catalog`) → 이번 사이클 V057(+V058) | — |

**사전 결정 사항 (2026-08-07 사용자 확정)**:

1. **방향**: Inbound·Outbound **둘 다** 설계하되 **Inbound 우선 구현** (M1=Inbound, M2=Outbound).
2. **인증**: **에이전트별 시크릿 키 + HMAC-SHA256 서명** — 재발급/폐기 지원, Outbound payload도 동일 시크릿으로 서명.
3. **Inbound 실행 모델**: **동기** — POST 후 실행 완료까지 대기, 결과 JSON 반환 (비동기 콜백은 후속).
4. **범위**: **풀스택** — 빌더 설정 탭 Webhook 섹션 실기능(키 발급/복사, URL 표시, 활성 토글, M2에서 outbound URL 등록+전송 이력).
5. **오픈 대상 지정**: 기존 필드·enum 변경 없이 **신규 1:1 테이블 `agent_webhook`로 독립 opt-in**
   (기존 설정 보존 — prefer-independent-optin 관례).

### 1.3 Related Documents

- 설정 탭 스텁의 유래: `docs/archive/2026-08/agent-settings-tab/` (Webhook 섹션 자리 예약 + "실기능은 별도 PDCA 사이클" 명시)
- 실행 파이프라인·관측: `docs/archive/2026-07/agent-recursion-limit/`, agent_run 계열 (run_id 관측 계약)
- 계약 확장 관례: `docs/wiki/conventions/additive-contract-extension.md` (additive·독립 opt-in)
- 라우터 지도: `docs/wiki/backend/api/router-map.md`
- 화면↔API 절단면: `docs/wiki/frontend/screens/agent-screens.md`

---

## 2. Scope

### 2.1 In Scope — M1: Inbound (우선 구현)

- [ ] **S1. DB — V057 `agent_webhook` 테이블 신설** (agent_definition 무변경):
      `id, agent_id(FK, UNIQUE — 에이전트당 1채널), enabled, secret_hash, secret_hint(끝 4자),`
      `outbound_url(NULL, M2), outbound_enabled(DEFAULT FALSE, M2), created_by, created_at, updated_at`
      — 테이블+전 컬럼 COMMENT 필수, FK에 CHARSET/COLLATE 명시 금지(ENGINE=InnoDB만), SQLAlchemy 모델 동반.
- [ ] **S2. 도메인 — 웹훅 검증 정책**: 서명 스킴(HMAC-SHA256, `{timestamp}.{raw_body}` 서명 대상),
      타임스탬프 허용창(±300초, 재생 공격 방어), 시크릿 생성 규칙(충분한 엔트로피, 예: 32바이트 urlsafe).
      stdlib(hmac/hashlib/secrets)만 사용 — domain 레이어 금지 사항(외부 API·DB) 저촉 없음.
- [ ] **S3. 관리 API (JWT, 소유자 전용)** — `agent_webhook_router`:
      - `POST /api/v1/agents/{agent_id}/webhook` — 활성화+키 발급 (**평문 시크릿은 이 응답 1회만** 반환, 이후 hint만)
      - `GET /api/v1/agents/{agent_id}/webhook` — 설정 조회 (enabled·hint·inbound URL·outbound 설정)
      - `POST /api/v1/agents/{agent_id}/webhook/rotate` — 재발급 (기존 키 즉시 무효, 새 평문 1회 반환)
      - `PATCH /api/v1/agents/{agent_id}/webhook` — enabled 토글 (M2에서 outbound_url·outbound_enabled 추가)
      - `DELETE /api/v1/agents/{agent_id}/webhook` — 채널 해제
- [ ] **S4. Inbound 공개 API (JWT 미적용)** — `webhook_public_router`:
      `POST /api/v1/webhooks/agents/{agent_id}` — 헤더 `X-Webhook-Timestamp`/`X-Webhook-Signature` 검증
      → 검증 실패 401, 미설정/비활성 404 → 성공 시 기존 `run_agent` use case로 **동기 실행**
      → `RunAgentResponse` 형태 결과 반환. 실행 주체는 **에이전트 소유자 신원**(user_id=owner),
      기본 stateless(호출마다 새 session), 요청 body에 `session_id` 명시 시 멀티턴 유지.
- [ ] **S5. 프론트 — 설정 탭 Webhook 섹션 실기능화**:
      스텁 → 활성 토글 + 키 발급/재발급(평문 1회 모달·복사 버튼·hint 표시) + inbound URL 표시/복사
      + "소유자 권한으로 실행됨" 경고문. types/services/hooks/constants(api.ts) 신설.
- [ ] **S6. 테스트 (TDD — Red 먼저)**:
      백엔드 — 서명 검증 정책 단위(유효/위조/만료 타임스탬프), 관리 API(발급·rotate 후 구키 무효·소유자 아님 403),
      inbound(정상 실행·401·404·disabled) / 프론트 — Webhook 섹션 단위 + MSW 통합(발급 플로우·토글).

### 2.2 In Scope — M2: Outbound (M1 완료 후 착수)

- [ ] **S7. DB — V058 `agent_webhook_delivery` 전송 로그**: 발송 대상 URL, run_id, 상태코드, 성공 여부,
      오류 메시지, 소요 시간, 시도 횟수 (COMMENT 규칙 동일).
- [ ] **S8. Outbound 발송**: 스케줄 실행·inbound 웹훅 실행 완료 시 `outbound_enabled`면 등록 URL로
      서명된 결과 payload POST (동일 시크릿 HMAC). 실패 시 재시도 3회(지수 백오프), 결과는 delivery 로그 기록.
      HTTP 클라이언트는 infrastructure 계층(httpx).
- [ ] **S9. 프론트 — outbound URL 등록 폼 + 최근 전송 이력 목록** (설정 탭 Webhook 섹션 내).
- [ ] **S10. 테스트**: 발송 성공/실패/재시도 단위(HTTP mock), delivery 로그 기록, URL 검증(http/https만).

### 2.3 Out of Scope (이번 사이클 제외)

- **비동기 실행 모델** (202+callback_url) — 동기 확정, 장시간 실행 수요 확인 후 후속
- **Rate limiting / 호출 쿼터 / IP allowlist** — 후속 (리스크 §5에 완화책 명시)
- SSE 스트리밍의 외부 노출 (inbound는 동기 JSON만)
- 에이전트당 다중 키 / 키 만료 정책 / 스코프 분리
- `attachments`(엑셀 첨부) 외부 호출 지원 — inbound 계약은 `query`(+`session_id`)만
- Telegram·MCP 서버 섹션 (설정 탭의 나머지 스텁 — 각자 별도 사이클)
- 웹훅 호출량 대시보드/통계 (ai_run 관측으로 기본 집계는 자동 확보됨)

---

## 3. Requirements

### 3.1 Functional Requirements — M1: Inbound

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 소유자가 웹훅 활성화 시 시크릿 키가 발급되고, 평문은 발급/재발급 응답에서 **1회만** 노출된다 (DB에는 해시+hint만 저장) | High | Pending |
| FR-02 | inbound 호출은 `X-Webhook-Timestamp`+`X-Webhook-Signature`(HMAC-SHA256) 검증을 통과해야 한다 — 서명 불일치·타임스탬프 ±300초 이탈 시 401 | High | Pending |
| FR-03 | 웹훅 미설정·비활성 에이전트로의 inbound 호출은 404 (존재 여부 비노출) | High | Pending |
| FR-04 | 검증 통과 시 에이전트가 소유자 신원으로 동기 실행되고 answer·run_id 등 결과 JSON이 반환된다 (기존 run 계약과 동형) | High | Pending |
| FR-05 | rotate 시 이전 키는 즉시 무효화된다 (구키 호출 401) | High | Pending |
| FR-06 | 관리 API는 에이전트 소유자만 접근 가능하다 (타인 403) | High | Pending |
| FR-07 | 설정 탭 Webhook 섹션에서 활성 토글·키 발급/재발급/복사·inbound URL 확인이 가능하다 | High | Pending |
| FR-08 | 웹훅 실행도 기존 ai_run 관측에 기록된다 (run_id 발급 — 기존 파이프라인 재사용으로 자동 충족 확인) | Medium | Pending |
| FR-09 | 기존 실행 경로(JWT run/stream)·설정 탭 다른 섹션 동작이 변하지 않는다 | High | Pending |

### 3.2 Functional Requirements — M2: Outbound

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-10 | 소유자가 outbound URL(http/https만 허용)을 등록·수정·비활성화할 수 있다 | High | Pending |
| FR-11 | 스케줄 실행·inbound 웹훅 실행 완료 시 outbound_enabled면 결과 payload가 서명되어 등록 URL로 POST된다 | High | Pending |
| FR-12 | 발송 실패 시 최대 3회 재시도(지수 백오프)하고, 모든 시도가 delivery 로그에 기록된다 | Medium | Pending |
| FR-13 | 발송 실패가 에이전트 실행 자체를 실패시키지 않는다 (발송은 부수 효과 — 오류 격리) | High | Pending |
| FR-14 | 설정 탭에서 최근 전송 이력(시각·상태·성공 여부)을 확인할 수 있다 | Medium | Pending |

### 3.3 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 보안 — 시크릿 | 평문 시크릿 DB 저장 금지(해시만), 로그·응답에 시크릿 미노출 (hint 제외), 서명 비교는 상수 시간(`hmac.compare_digest`) | 코드 리뷰 + 단위 테스트 |
| 보안 — 공개 표면 | inbound 라우터는 JWT 의존 없이 서명 검증만으로 인가 — 검증 이전에 DB 부하 큰 작업 금지 | 라우터 의존성 검사 + 테스트 |
| 레이어 준수 | 서명 정책=domain(stdlib만), use case=application, HTTP 발송·해시 저장=infrastructure, 라우터=interfaces | verify-architecture 스킬 |
| DDL | V057/V058 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 명시 금지, SQLAlchemy `comment=` 동반 | `tests/db/test_migration_ddl_comments.py` |
| TDD | 테스트 선행 (Red → Green), 프론트 MSW per-file listen·`--pool=threads` | 신규 테스트 파일 동반 |
| 회귀 안전 | 기존 pytest·vitest 무회귀 (사전 실패 목록 제외 기준) | 격리 실행 |
| API 계약 동기화 | 신규 엔드포인트 → `idt_front/src/constants/api.ts` + types/services/hooks 동반 (루트 CLAUDE.md §4-1) | api-contract-sync 체크 |

---

## 4. Success Criteria

### 4.1 Definition of Done — M1

- [ ] 설정 탭에서 웹훅 활성화 → 발급 키로 curl에서 서명 생성 → inbound POST → 에이전트 답변 JSON 수신 (E2E 수동)
- [ ] 잘못된 서명·만료 타임스탬프 → 401 / 비활성 토글 후 호출 → 404 (테스트 단언)
- [ ] rotate 후 구키 호출 401, 신키 호출 정상 (테스트 단언)
- [ ] 웹훅 실행이 ai_run 관측 화면에 잡힘 (수동 확인)
- [ ] 소유자 아닌 사용자의 관리 API 접근 403 (테스트 단언)

### 4.2 Definition of Done — M2

- [ ] 스케줄 실행 완료 시 로컬 수신 서버(테스트용)로 서명된 payload 도착 + 서명 검증 재현 (E2E 수동)
- [ ] 수신 서버 다운 시 3회 재시도 후 실패 로그 기록, 에이전트 실행 자체는 성공 유지 (테스트 단언)

### 4.3 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, config 하드코딩 금지 (허용창·재시도 횟수는 상수/설정으로)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 공개 엔드포인트 노출 → 무차별 대입·DoS | High | Medium | 시크릿 32바이트 엔트로피 + HMAC(추측 불가), 검증 실패 시 조기 401(실행 비용 미발생), 미설정 404로 존재 비노출. rate limit은 명시적 후속 — plan에 한계로 기록 |
| 동기 실행이 수십 초 → 호출자/프록시 타임아웃 | Medium | High | 응답 지연 특성·권장 클라이언트 타임아웃(120s) 문서화(응답 헤더/설정 탭 안내문). 장시간 에이전트는 max_iterations 하향 권고. 비동기 모델은 후속 확장 여지로 설계(콜백 필드 예약 없음 — YAGNI) |
| 소유자 신원 실행 → 외부 호출자가 소유자 권한 KB/도구 접근 | High | Medium | opt-in 명시 + 설정 탭에 "이 에이전트는 내 권한으로 실행됩니다" 경고문 + 키 관리 UX(1회 노출·rotate). 부서/공용 문서 노출 범위는 소유자 책임 모델로 문서화 |
| Outbound SSRF (내부망 URL 등록) | Medium | Medium | http/https 스킴만 허용 + URL 형식 검증. 내부 IP 대역 차단 여부는 Design에서 확정 (사내망 수신이 정상 유스케이스라 일괄 차단 불가 — 협의 필요) |
| Outbound 발송 실패가 실행 트랜잭션 오염 | Medium | Low | 발송은 실행 완료 후 부수 효과로 격리(FR-13), 예외 삼킴+로그. Repository commit 규칙 준수 |
| 시크릿 평문 1회 노출 UX — 사용자가 복사 놓침 | Low | Medium | 발급 모달에 복사 버튼+재확인, 놓치면 rotate로 재발급 가능함을 안내 |
| 공개 라우터가 기존 인증 미들웨어 전제와 충돌 | Medium | Low | 신규 별도 라우터 파일로 격리 등록, 기존 라우터 무변경. 무토큰 4xx 실측 테스트 포함 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| opt-in 저장 위치 | agent_definition 컬럼 추가 / 신규 1:1 테이블 | **신규 `agent_webhook` 테이블** | 기존 스키마·update 화이트리스트 무변경(회귀 0), 시크릿·outbound 설정 등 응집 필드가 많아 테이블 분리가 자연스러움. 독립 opt-in 관례 부합 |
| 인증 방식 | Bearer 키 단순 비교 / URL 토큰 / **키+HMAC 서명** | **키+HMAC-SHA256+타임스탬프** | 사용자 확정. 전송 중 키 비노출·재생 공격 방어·outbound 서명 재사용 — 표준 웹훅 보안(GitHub/Slack/Stripe 동형) |
| 실행 모델 | 동기 / 비동기(202+콜백) / 혼합 | **동기** | 사용자 확정. 호출자 구현 최소, 기존 run use case 그대로 재사용. 타임아웃 리스크는 문서화로 수용 |
| 실행 주체 신원 | 소유자 / 전용 시스템 계정 / 호출자 매핑 | **소유자(owner) 신원** (Design 재확인) | 권한·KB 접근·관측이 기존 모델 그대로 동작. 전용 계정은 권한 체계 신설 필요 — YAGNI. 경고문으로 리스크 상쇄 |
| inbound 세션 | 매 호출 새 세션 / session_id 수용 | **기본 새 세션 + `session_id` optional 수용** | stateless 기본이 외부 계약으로 단순·안전, 멀티턴 필요 시스템만 opt-in |
| Outbound 발송 시점 | 스케줄만 / 스케줄+웹훅 실행 / 모든 실행 | **스케줄 + inbound 웹훅 실행** (Design 확정) | "외부 연동 채널의 실행"에 한정 — 사내 UI 수동 실행까지 발송하면 노이즈. Design에서 최종 확정 |
| 전송 로그 | 없음 / 신규 테이블 | **V058 delivery 로그 (M2)** | 외부 발송은 실패 진단 수단이 필수 — "라우터 배선 ≠ 실행 구현" 교훈의 관측 대응물 |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── db/migration/
│   ├── V057__create_agent_webhook.sql              # S1 (M1)
│   └── V058__create_agent_webhook_delivery.sql     # S7 (M2)
├── src/
│   ├── domain/agent_webhook/                       # S2: 서명 정책·시크릿 규칙 (stdlib만)
│   ├── application/agent_webhook/                  # S3·S4·S8: use cases + schemas
│   ├── infrastructure/
│   │   ├── db/ (모델·repository)                   # S1·S7
│   │   └── webhook/ (outbound sender, httpx)       # S8 (M2)
│   └── api/routes/
│       ├── agent_webhook_router.py                 # S3: 관리 (JWT)
│       └── webhook_public_router.py                # S4: inbound (JWT 미적용, 별도 등록)
└── tests/ (domain·application·api 각 대응)          # S6·S10

idt_front/src/
├── constants/api.ts                                # 신규 엔드포인트 상수
├── types/agentWebhook.ts                           # 신규 타입
├── services/ + hooks/                              # 웹훅 설정 조회·발급·토글 (M2: 이력)
├── components/agent-builder/settings/
│   ├── SettingsPanel.tsx                           # Webhook 스텁 → 섹션 컴포넌트 교체
│   └── WebhookSection.tsx (+test)                  # S5·S9: 신설
└── __tests__/ (MSW 통합)                            # S6·S10
```

> 서명 대상 문자열 포맷·헤더 명세·inbound 에러 계약·SSRF 차단 수준·outbound payload 스키마는 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] DDL: 테이블+전 컬럼 COMMENT, FK에 CHARSET/COLLATE 금지 (V037 선례·errno 3780), SQLAlchemy `comment=` 동반 — V057/V058 적용
- [x] DB 세션: Repository 내 commit 금지, use case 단일 세션 (`docs/rules/db-session.md`)
- [x] 로깅: StructuredLogger, 시크릿 마스킹, 스택 트레이스 필수 (`docs/rules/logging.md`)
- [x] 프론트 테스트 관례: vitest `--pool=threads`, MSW per-file listen 3종 훅, jsdom noValidate 함정
- [x] API 계약 동기화 대상 — 신규 라우터 2본이므로 `api-contract-sync` 체크리스트 수행 필요
- [ ] Design 단계 확정 항목: 서명 명세(헤더명·서명 문자열 포맷), 실행 주체 신원 최종 확인, outbound 발송 시점 범위, SSRF 차단 수준, inbound 요청/응답 스키마 상세
