# pii-masking 설계-구현 Gap 분석 (Check)

> **Feature**: pii-masking
> **Date**: 2026-06-30
> **기준 문서**: [pii-masking.design.md](../02-design/features/pii-masking.design.md)
> **분석 에이전트**: bkit:gap-detector
> **Match Rate**: **100%** (✅ iterate 후, in-scope 기준 / 1차 85% → 2차 100%)

---

## 1. 종합 점수

| 항목 | 1차 | 2차(iterate 후) | 상태 |
|------|:---:|:---:|:----:|
| 설계 일치 (Match Rate) | 85% | **100%** | ✅ |
| DDD 레이어 준수 | 100% | 100% | ✅ |
| 컨벤션 준수 (naming/LOG-001/mock금지) | 100% | 100% | ✅ |

**1차 산출**: 30개 항목 중 ✅23 + ⚠️5(×0.5) + ❌2 = 25.5 / 30 = **85.0%**
**2차 산출**: Gap #2(main.py DI) 범위 제외 → 분모 29. 6개 Gap 전부 해소 → 29/29 = **100%**
**테스트**: 55개 통과 (1차 45 → +10), ruff 통과.

> 범위 제외(정상): 그래프 배선(design §2.2/§11.3) — `rag_agent/tools.py`, `run_agent_use_case.py`, `MiddlewareBuilder`. Gap #2(main.py DI)는 사용자 결정으로 후속 배선 plan 이관. 모두 Gap으로 계산하지 않음.

---

## 2. Gap 처리 결과 (1차 → 2차)

| # | Gap | 1차 | 처리 | 2차 |
|---|-----|:---:|------|:---:|
| 1 | detector 정규식 예외 가드 (보안) | ❌ | mask/unmask try/except, `MASK_FAILURE_PLACEHOLDER` fail-closed | ✅ |
| 3 | CARD 13~19자리 | ⚠️ | `CARD_PATTERN` 가변 자릿수 확장(Amex15/Diners14) | ✅ |
| 4 | EMAIL TLD 최소 길이 검증 | ⚠️ | `policies.email_valid` 추가, is_valid 적용 | ✅ |
| 5 | `PiiMaskingService` 생성자 | ⚠️ | 설계 §5.3에서 `policy` 인자 제거(문서 정합) | ✅ |
| 6 | 고아 placeholder 처리 | ⚠️ | `_redact_orphan_placeholders` (WARN + `[REDACTED_<TYPE>]`) | ✅ |
| 7 | session_id 부재 처리 | ⚠️ | 설계 §6 문구를 구현 동작에 맞춰 정정 | ✅ |
| 2 | main.py 팩토리 DI 조립 | ❌ | **범위 제외(사용자 결정)** → 후속 배선 plan 이관 | — |

---

## 3. Scope Creep
**유의미한 creep 없음.** 추가분은 모두 합리적 보조:
- `TokenVault.size` (로깅용 개수, LOG-001 보조)
- `TokenVaultRegistry.clear` (vault 수명 관리)
- `PiiMaskingConfig.from_settings` (§10.3 config 파싱 의도 구현)

---

## 4. DDD 레이어 검증
**위반 0건 (100% 준수).** domain→infra/app 역참조 없음. detector는 포트로 주입(application→domain only, infra→domain only).

---

## 5. 결론

in-scope 6개 Gap 전부 해소 → **Match Rate 100%**. DDD/컨벤션 100% 유지. 테스트 55개 통과.
다음 단계: `/pdca report pii-masking` (완료 보고서). Gap #2(main.py DI)와 그래프 배선은 후속 배선 plan에서 처리.

---

## Version History
| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-06-30 | gap-detector 1차 분석 (Match Rate 85%) |
| 0.2 | 2026-06-30 | 수동 iterate 후 재검증 (Match Rate 100%, 6 Gap 해소) |
