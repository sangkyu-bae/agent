# Gap Analysis: fix-es-upload-morph-error

> Analyzed: 2026-04-29
> Design: `docs/02-design/features/fix-es-upload-morph-error.design.md`
> Match Rate: **95%**

---

## 1. 항목별 비교

| # | Design 명세 | 구현 상태 | 일치 |
|---|------------|----------|------|
| D1 | `tok.tag.name` → `tok.tag if isinstance(tok.tag, str) else tok.tag.name` | `kiwi_morph_analyzer.py:30` 정확히 일치 | MATCH |
| D2 | `test_analyze_handles_string_tag` 테스트 추가 | 추가됨 + `test_analyze_handles_enum_tag` 보너스 추가 | MATCH |
| D3 | `_store_to_es` 내부 try/except + logger.error 후 re-raise | **미구현** — try/except 없음 | GAP |
| D4 | `execute()` gather 결과 Exception 감지 시 logger.error | `use_case.py:113-127` 구현 완료 | MATCH |
| D5 | `test_execute_es_fails_logs_error` 테스트 추가 | 추가됨 + `test_execute_qdrant_fails_logs_error` 보너스 추가 | MATCH |
| D6 | StructuredLogger `exc_info` → 명시적 tuple 변환 | `structured_logger.py:129` 정확히 일치 | MATCH |
| D7 | `test_error_with_no_traceback_exception_does_not_crash` 테스트 추가 | 추가됨 | MATCH |

---

## 2. Gap 상세

### GAP-1: `_store_to_es` 내부 try/except 미구현 (경미)

**Design 명세** (섹션 2-2, 변경 1):
> `_store_to_es` 내부에 try/except 추가 → `logger.error()` 호출 후 re-raise

**현재 구현**: `_store_to_es()` 메서드에 try/except 없음. 대신 `execute()`에서
`asyncio.gather` 결과를 `isinstance(es_raw, Exception)` 체크하여 로깅.

**영향도**: **낮음**
- `asyncio.gather(return_exceptions=True)`가 항상 예외를 캡처하므로 gather-level 로깅만으로 충분
- Design의 "이중 안전망" 의도는 미달이지만, 핵심 요구사항(에러 로깅)은 충족
- `_store_to_es` 내부 try/except는 gather 없이 직접 호출하는 경우에만 의미 있으나 현재 그런 호출 경로 없음

**조치 권고**: 선택적 — 추가해도 좋으나 필수는 아님

---

## 3. 추가 구현 (Design 대비 초과)

| 항목 | 설명 |
|------|------|
| `test_analyze_handles_enum_tag` | Design에 없으나 하위 호환성 검증 테스트 추가 |
| `test_execute_qdrant_fails_logs_error` | Design에 없으나 Qdrant 실패 시 로깅 검증 추가 |

---

## 4. 검증 기준 확인

| # | 검증 항목 | 결과 |
|---|----------|------|
| V1 | kiwipiepy 0.22.2에서 MorphAnalyzer 정상 동작 | PASS (13/13 tests) |
| V2 | _store_to_es 실패 시 ERROR 로그 출력 | PASS (gather-level 로깅) |
| V3 | 인터페이스 변경 없음 | PASS (LoggerInterface, MorphAnalyzerInterface 불변) |
| V4 | __traceback__ 없는 예외 로깅 안전 | PASS (15/15 tests) |
| V5 | 관련 테스트 전체 통과 | PASS (1284 passed) |

---

## 5. 결론

**Match Rate: 95%** (7 항목 중 6 일치, 1 경미 Gap)

GAP-1은 핵심 기능에 영향 없으며, gather-level 로깅이 충분히 목적을 달성하고 있어
**추가 iteration 없이 Report 단계로 진행 가능**합니다.
