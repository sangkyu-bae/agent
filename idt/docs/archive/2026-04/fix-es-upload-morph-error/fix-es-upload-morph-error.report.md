# Completion Report: fix-es-upload-morph-error

> Completed: 2026-04-29
> PDCA Cycle: Plan → Design → Do → Check(95%) → Report
> Iteration Count: 0 (first pass 95%, no iteration needed)

---

## 1. Summary

`POST /api/v1/documents/upload-all` 호출 시 ES 색인이 100% 실패하고
에러 로그도 출력되지 않던 운영 장애를 수정했다.

**근본 원인**: kiwipiepy 0.22.2에서 `tok.tag`가 enum이 아닌 str을 반환하는데,
`kiwi_morph_analyzer.py`가 `.name` 속성(enum 전용)을 호출하여 `AttributeError` 발생.
이 예외가 `asyncio.gather(return_exceptions=True)`에 의해 조용히 캡처되어 로그 없이 묻혔다.

---

## 2. Changes

### 2-1. KiwiMorphAnalyzer 호환성 수정

| 항목 | 내용 |
|------|------|
| 파일 | `src/infrastructure/morph/kiwi_morph_analyzer.py:30` |
| 변경 전 | `pos=tok.tag.name` |
| 변경 후 | `pos=tok.tag if isinstance(tok.tag, str) else tok.tag.name` |
| 영향 | ES 색인 정상화 (kiwipiepy 0.22.2 호환), 이전 버전 하위 호환 유지 |

### 2-2. asyncio.gather 결과 에러 로깅

| 항목 | 내용 |
|------|------|
| 파일 | `src/application/unified_upload/use_case.py:113-127` |
| 변경 | `asyncio.gather` 결과가 Exception인 경우 `logger.error()` 호출 |
| 영향 | Qdrant/ES 저장 실패 시 스택 트레이스 포함 ERROR 로그 출력 |

### 2-3. StructuredLogger exc_info 안정성 개선

| 항목 | 내용 |
|------|------|
| 파일 | `src/infrastructure/logging/structured_logger.py:129` |
| 변경 전 | `exc_info=exception` (Exception 인스턴스 직접 전달) |
| 변경 후 | `exc_info=(type(exception), exception, exception.__traceback__)` |
| 영향 | StructuredFormatter와의 tuple 계약 명시적 보장 |

---

## 3. Test Results

| 테스트 스위트 | 결과 | 추가된 테스트 |
|-------------|------|-------------|
| `tests/infrastructure/morph/` | 13/13 passed | `test_analyze_handles_string_tag`, `test_analyze_handles_enum_tag` |
| `tests/application/unified_upload/` | 13/13 passed | `test_execute_es_fails_logs_error`, `test_execute_qdrant_fails_logs_error` |
| `tests/infrastructure/logging/` | 15/15 passed | `test_error_with_no_traceback_exception_does_not_crash` |
| 전체 관련 테스트 | **1284/1284 passed** | — |

---

## 4. Gap Analysis Summary

| Match Rate | Gap 수 | 심각도 |
|-----------|--------|--------|
| **95%** | 1건 | 경미 |

**GAP-1**: Design에서 `_store_to_es` 내부 try/except(이중 안전망)를 명세했으나,
구현에서는 `execute()` gather-level 로깅만 적용. `_store_to_es`가 `asyncio.gather`를
통해서만 호출되므로 기능적으로 동일한 효과.

---

## 5. Files Changed

| 파일 | 변경 유형 | 줄 수 |
|------|----------|------|
| `src/infrastructure/morph/kiwi_morph_analyzer.py` | 수정 | 1줄 |
| `src/application/unified_upload/use_case.py` | 수정 | +14줄 |
| `src/infrastructure/logging/structured_logger.py` | 수정 | 1줄 |
| `tests/infrastructure/morph/test_kiwi_morph_analyzer.py` | 추가 | +12줄 |
| `tests/application/unified_upload/test_use_case.py` | 추가 | +54줄 |
| `tests/infrastructure/logging/test_structured_logger.py` | 추가 | +8줄 |

---

## 6. Architecture Compliance

- Layer 규칙 위반: **없음**
- Interface 변경: **없음** (LoggerInterface, MorphAnalyzerInterface 불변)
- API 계약 변경: **없음** (UnifiedUploadResponse 스키마 동일)
- 기존 테스트 회귀: **없음**

---

## 7. Before / After

**Before**:
```json
{
  "es": { "status": "failed", "error": "'str' object has no attribute 'name'" },
  "status": "partial"
}
// 서버 로그: 에러 관련 출력 없음
```

**After**:
```json
{
  "es": { "status": "success", "indexed_count": 14 },
  "status": "completed"
}
// 실패 시 서버 로그: ERROR + 스택 트레이스 출력
```

---

## 8. Lessons Learned

1. **라이브러리 버전 업데이트 시 반환 타입 변경 주의** — kiwipiepy의 `tok.tag`가 enum에서 str로 변경된 것이 런타임에서만 발견됨. 방어적 타입 체크(`isinstance`)로 하위 호환성 확보.

2. **`asyncio.gather(return_exceptions=True)` 사용 시 반드시 에러 로깅** — 예외가 조용히 캡처되므로 gather 결과를 검사하여 명시적으로 로깅해야 운영 모니터링이 가능.
