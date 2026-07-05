# pii-masking 완료 보고서 (PDCA Report)

> **Feature**: pii-masking — 가역 PII 마스킹 엔진 모듈
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-06-30
> **Status**: Completed (Match Rate 100%)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | LangGraph 경로(`create_react_agent`)에 질문·검색 데이터의 개인정보를 외부 LLM 전송 전 마스킹하는 단계가 없어 PII 유출 위험이 있었다. |
| **Solution** | 프레임워크 독립 **가역 마스킹 엔진**(`domain/application/infrastructure/pii_masking`)을 TDD로 구현. 한국 PII 5종을 정규식+정책으로 탐지해 `[RRN_1]` placeholder로 치환하고, 응답에서 원복한다. |
| **Function/UX Effect** | 외부 LLM엔 원본 PII 미전달, placeholder 일관성으로 RAG 추론 품질 유지, 사용자엔 원복 응답 제공. 미매핑·고아 PII는 `[REDACTED_<TYPE>]`로 2차 방어. |
| **Core Value** | 금융/정책 문서 도메인의 외부 LLM 경계 PII 유출 위험을 차단하는 재사용 가능한 단일 책임 모듈 확보. |

### Value Delivered (실측)

| 관점 | 지표 |
|------|------|
| Problem 해소 | 외부 LLM 경계 PII 마스킹 0 → 엔진 모듈 완성 (입력·검색결과·응답 3지점 포트 제공) |
| Solution 품질 | Match Rate **100%** (1차 85% → iterate 후 100%), DDD 100%, 컨벤션 100% |
| 구현 규모 | 신규 소스 7파일(domain 4 + app 2 + infra 1), config 3필드, 테스트 4파일 **55 케이스 전부 통과** |
| Core Value 검증 | mask→unmask round-trip 정합, 멀티턴 session 일관성, fail-closed, 고아 placeholder redact 테스트로 입증 |

---

## 1. PDCA 사이클 요약

| Phase | 산출물 | 결과 |
|-------|--------|------|
| Plan | `docs/01-plan/features/pii-masking.plan.md` | 4개 결정(커스텀 모듈·한국 PII·가역·3지점), Open Q 3건 |
| Design | `docs/02-design/features/pii-masking.design.md` | OQ 확정(카드 Luhn/계좌 휴리스틱·session_id 스코프·`[REDACTED_*]`), 레이어·포트·탐지규칙 명세 |
| Do | `src/{domain,application,infrastructure}/pii_masking/` | TDD Red→Green, 45 테스트 |
| Check | `docs/03-analysis/pii-masking.analysis.md` | gap-detector 1차 85% |
| Act-1 | (수동 iterate) | 6 Gap 해소, 재검증 100%, 55 테스트 |

---

## 2. 구현 결과

### 2.1 모듈 구조 (Thin DDD)

```
domain/pii_masking/        schemas(PiiType/PiiMatch/TokenVault/Registry), patterns, policies, interfaces
application/pii_masking/    schemas(PiiMaskingConfig), pii_masking_service(mask/unmask)
infrastructure/pii_masking/ regex_detectors(RegexPiiDetector)
config.py / .env.example    pii_masking_enabled / _types / _output_redact
tests/{domain,application,infrastructure}/pii_masking/  55 cases
```

### 2.2 핵심 기능

- **가역 마스킹**: `mask()` placeholder 치환 + session vault 누적 → `unmask()` 원복
- **한국 PII 5종**: 주민번호(생년월일·성별코드 검증), 휴대폰/유선, 이메일(TLD 검증), 카드(13~19자리+Luhn), 계좌(휴리스틱)
- **탐지 우선순위·겹침 처리**: RRN→CARD→PHONE→EMAIL→ACCOUNT, span 점유 기반
- **session_id 스코프**: 멀티턴 동일 PII 일관성
- **방어**: 탐지 예외 시 fail-closed(`[PII_MASKING_FAILED]`), 미매핑·고아 PII `[REDACTED_<TYPE>]`
- **보안 로깅**: 원본/vault 값 미기록(개수·타입만), LOG-001 준수

---

## 3. 품질 지표

| 항목 | 결과 |
|------|------|
| 설계 일치 (Match Rate) | 100% |
| DDD 레이어 (domain→infra/app 역참조) | 0건 위반 |
| 단위 테스트 | 55 통과 (mock 금지, 실제 객체/명시적 fake) |
| Lint (ruff) | 통과 |
| 컨벤션 (naming/40줄/if중첩/하드코딩 금지) | 준수 |

---

## 4. 범위 밖 (후속 작업)

이번 산출물은 **엔진 + 포트**까지이며, 다음은 의도적으로 제외:

1. **production 그래프 배선** — `rag_agent/tools.py:_format_results`(검색결과), `run_agent_use_case.py` final answer 노드(응답), `general_chat/use_case.py`
2. **v2 미들웨어 연동** — `MiddlewareBuilder`의 `PIIMiddleware(detector=RegexPiiDetector.detect)` custom detector 주입
3. **main.py 팩토리 DI 조립** (Gap #2, 사용자 결정으로 이관)
4. **vault 영속화** — `TokenVaultStorePort` 구현(Redis 등) + 암호화

→ 후속 plan: `pii-masking-integration` (배선 + DI + 영속화)

---

## 5. 학습 포인트

- production이 `create_react_agent`(langgraph 0.2)라 langchain v1.0 빌트인 `PIIMiddleware`를 직접 못 쓰는 제약 → 프레임워크 독립 커스텀 모듈이 정답이었다.
- 검증 로직을 detector(infra)에 두어 service 생성자를 단순화 → 설계보다 구현이 합리적이었고, 문서를 구현에 맞춰 정합(Gap #5).
- 가역 마스킹의 핵심 위험은 "응답 원복 실패 시 placeholder 노출" → 고아 placeholder redact로 2차 방어 추가(Gap #6).

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-30 | PDCA 완료 보고서 (Match Rate 100%, 55 테스트 통과) |
