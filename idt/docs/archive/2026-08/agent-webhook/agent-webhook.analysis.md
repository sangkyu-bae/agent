# Agent Webhook Gap Analysis (Check)

> **Feature**: agent-webhook (M1 Inbound)
> **Date**: 2026-08-07
> **Analyzer**: gap-detector
> **Design SoT**: `docs/02-design/features/agent-webhook.design.md`
> **Match Rate**: **93.3%** (48.5 / 52) — 임계 90% 통과, Act 반복 불요
> **범위**: Design §2~§8 (M1). §9 M2(Outbound)·Plan FR-10~14는 명시 이월 범위로 제외

---

## 1. 요약

- **기능 결손 0건** — DDL·domain·infrastructure·application·interfaces·DI·프론트·테스트 7계층 전부 설계대로 구현.
- **보안 금지 사항 4종 전부 통과**: 시크릿 로그 인자 미전달·조회 응답 미노출, 공개 라우터 인증 의존성 부재(무토큰 200 실측 테스트 존재), Repository 내 commit 없음.
- 잔여 Gap 7건 중 코드 수정 필수 항목 **없음** — 4건은 설계 문서 측 정정 대상, 2건은 저위험 견고성 개선, 1건(Medium)은 E2E 수동 검증 이월.

## 2. 그룹별 점수

| 그룹 | 항목 | 획득 | 비고 |
|---|:--:|:--:|---|
| §2 결정 D1~D10 | 10 | 9.0 | D6 0.5(문자열 매칭 분기), D10 0.5(프론트 문구 상수 위치) |
| §3 DDL/모델 | 6 | 6.0 | COMMENT·FK CASCADE·UNIQUE·CHARSET 부재·comment= 미러 전부 일치 |
| §4-3 UseCase 6종 | 6 | 6.0 | 시그니처·예외·검증 순서(D5) 일치 |
| §4-4 API 계약 | 6 | 6.0 | 경로·상태코드·응답 필드·raw body 전달 일치 |
| §4-5 DI | 3 | 3.0 | 팩토리+오버라이드 6종+라우터 2본 등록 |
| §5 프론트 | 9 | 9.0 | D9 create 안내·시크릿 1회 모달·hint·토글·rotate/삭제 confirm·경고문, Bearer 문구 폐기 grep 0건 |
| §6 테스트 | 7 | 7.0 | 설계 케이스 전량 대응 (백엔드 58·프론트 45 통과) |
| 금지 사항 | 4 | 4.0 | §1 요약 참조 |
| 설계 문서 정합 | 2 | 0.5 | §4-1 repo 경로·§4-2 hash() 잔재 (아래 G2·G3) |
| §7-7 E2E 수동 | 1 | 0.0 | G7 이월 |
| **합계** | **52** | **48.5** | **93.3%** |

## 3. Gap 목록

| ID | Gap | 심각도 | 처리 방침 |
|---|---|:--:|---|
| G1 | D10 절반 미준수 — 웹훅 안내 문구가 `constants/agentSettings.ts`가 아닌 `WebhookSection.tsx` 로컬 상수(`INFO_TEXT`) | Low | 수용 — 단일 소비처 로컬 상수가 응집상 자연스러움. 문서 측 D10 문구 완화로 종결 |
| G2 | Design §4-2에 `WebhookSecretPolicy.hash()`가 남아있음 — D2(평문 저장) 확정과 모순되는 설계 잔재 | Low(문서) | Report에서 설계 정정 기록 (코드가 정답) |
| G3 | repo 경로: 설계 `infrastructure/db/repositories/…` vs 구현 `infrastructure/agent_webhook/repository.py` | Low(문서) | 구현이 agent_schedule 선례 준수 — 설계 경로 오기로 기록 |
| G4 | `WEBHOOK_INBOUND` 상수 명칭 차이(설계 `WEBHOOK_INBOUND_PATH`) + 현재 미사용 | Trivial | 유지 (M2·외부 안내 문서용 예약) — 명칭은 구현 기준 |
| G5 | 409/404 분기가 예외 메시지 `"이미"` 부분문자열 의존 — 문구 변경 시 조용히 404 퇴화 | Low | 수용 (agent_builder_router 기존 관례와 동일). M2에서 전용 예외 승격 검토 |
| G6 | SettingsPanel prop: 설계 `agentId?: string` vs 구현 `agentId: string \| null` 필수 | Info | 기능 동등 — 필수 prop이 누락 실수를 타입으로 차단(우위). 문서 정정 |
| G7 | **E2E 수동 검증 미수행** (V057 적용 → 활성화 → curl 서명 호출 → ai_run 관측, rotate 후 구키 401) | **Medium** | 이월 — V057 적용이 선행 조건. 배포 전 체크리스트 등재 |

**설계 외 추가 구현** (회귀 위험 없음, 설계 의도 보강): `WebhookBadRequestError` 전용 예외, `extractWebhookError` 프론트 헬퍼, `INBOUND_PATH_TEMPLATE` 상수화.

## 4. 판정

- Match Rate 93.3% ≥ 90% → **Check 통과**. `pdca iterate` 불요.
- 다음 단계: `/pdca report agent-webhook`.
- 배포 전 필수: **V057 마이그레이션 적용** + G7 E2E 체크리스트.
- M2(Outbound) 착수 준비 확인: `WebhookSignaturePolicy.sign()` 재사용 가능, V057에 outbound 컬럼 선포함, `UpdateWebhookRequest` 확장 지점 명확.
