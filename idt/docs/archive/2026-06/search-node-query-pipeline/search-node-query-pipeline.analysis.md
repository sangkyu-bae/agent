# Gap Analysis: search-node-query-pipeline

> Created: 2026-06-10
> Phase: Check
> Plan: `docs/01-plan/features/search-node-query-pipeline.plan.md`
> Design: `docs/02-design/features/search-node-query-pipeline.design.md`
> Analyzer: bkit:gap-detector
> **Match Rate: 96.4% (27/28) — 합격 (≥90%)**

---

## 1. Match Rate 산정

| 검증 영역 | 항목 수 | 일치(✅) | 부분(⚠️) | 불일치(❌) |
|-----------|:------:|:------:|:------:|:------:|
| 설계 결정 D1~D6 | 6 | 6 | 0 | 0 |
| §2 변경 상세 2-1~2-6 | 6 | 5 | 1 | 0 |
| §3 실패 분기 매트릭스 | 5 | 5 | 0 | 0 |
| Plan FR-01~FR-11 | 11 | 11 | 0 | 0 |
| **합계** | **28** | **27** | **1** | **0** |

**Match Rate = 27 / 28 = 96.4%** (부분 일치 0.5 가중 시 98.2%)

유일한 ⚠️는 D3 LLM 수명에 대한 **의도된 개선 구현**(설계 "compile()당 1회 생성" → 구현 "인스턴스 캐시 + 재귀/반복 재사용")으로, 설계 목적을 더 잘 충족하므로 결함 아님.

---

## 2. 항목별 비교 (요약)

### 설계 결정 D1~D6

| 항목 | 구현 위치 | 상태 | 비고 |
|------|----------|:----:|------|
| D1 마지막 시도 validate 생략 | `search_pipeline.py` `_search_with_validation` | ✅ | structured 3회(rewrite1+validate2) 테스트로 고정 |
| D2 메시지 규약 중앙화 | `search_pipeline.py` 정의 + compiler alias import | ✅ | 기존 중복 정의 삭제 확인 |
| D3 파이프라인 LLM 수명 | `_resolve_pipeline_llm` + `_pipeline_llm_cache` | ⚠️→✅ | 인스턴스 캐시로 개선 구현 (설계 문구 동기화 완료) |
| D4 도구 예외 시 재시도 | `if not ok: continue` + `_safe_search` | ✅ | 일시 장애 자동 복구 테스트 |
| D5 rewrite 입력 | `latest_user_question`(피드백 스킵) + `_collect_context` | ✅ | 6개/500자 상수 일치 |
| D6 SupervisorState 불변 | 반환 dict 기존 키 + STEP_OUTPUT_SUMMARY_KEY만 | ✅ | 신규 state 키 없음 |

### §2 변경 상세 / §3 실패 분기 / FR-01~11

- 2-1~2-6 모두 구현 일치 (config 기본값 openai/gpt-4o-mini/4000, main.py 주입, .env.example 포함)
- 실패 분기 5건(LLM 생성/rewrite/도구/validate/compress) 전부 graceful fallback 구현 + 전용 테스트
- Plan FR-01~FR-11 전 항목 ✅ — 상세 비교표는 gap-detector 원본 분석 참조 (본 문서 §1~2가 요약본)

---

## 3. Gap 목록 (High/Medium 0건)

| # | 심각도 | 항목 | 차이 | 조치 |
|---|:------:|------|------|------|
| G1 | Low | D3 문구 | 설계 "compile()당 1회" vs 구현 "인스턴스당 1회 캐시" | ✅ 설계 문서 문구 동기화 완료 (2026-06-10) |
| G2 | Low | 의사코드 헬퍼명 | `_last_message_text(messages)` vs `_message_text(messages[-1])` | 동작 동일 — 조치 불요 |
| G3 | Low | main.py 타임존 | 설계 `datetime.now(timezone.utc)` vs 구현 `datetime.now()` | 인라인 엔티티의 미사용 필드 — 무영향, 보류 |

## 4. 설계 외 추가 구현 (모두 설계 의도 강화 방향)

| # | 항목 | 평가 |
|---|------|------|
| A1 | `_SearchLoopResult` 데이터클래스 — 루프 결과 캡슐화 | 40줄 제한·가독성 (설계 권고 이행) |
| A2 | 단계함수 `tuple[값, llm_chars]` 반환 — 토큰 누적 타입 안전 | FR-08 강화 |
| A3 | `search_node executing` 구조화 로그 | FR-09 보강 |
| A4 | 검색 실패 메시지 압축 제외(`loop.ok` 가드) + 전용 테스트 | 암묵 규칙 명시화 |
| A5 | `_resolve_pipeline_llm` 캐시 + wiring 테스트 4건 | D3 hardening |

---

## 5. 검증 근거

- 테스트: 신규 36개 (policy 10 + pipeline 22 + wiring 4) + 회귀 `tests/application/agent_builder` 307 passed + `test_analyze_user_context` 9 passed
- NFR: 최악 LLM 추가 호출 4회 (Plan NFR ≤5 충족·개선), 호출 횟수 테스트로 회귀 방지
- 레이어 규칙: domain policy 순수성(LLM/도구 미참조), search_pipeline infrastructure import 없음, print() 미사용

## 6. 종합 판정

**합격 — Match Rate 96.4% ≥ 90%.** `/pdca iterate` 불요.

다음 단계: `/pdca report search-node-query-pipeline`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-10 | gap-detector 분석 결과 기록, G1 문서 동기화 | 배상규 |
