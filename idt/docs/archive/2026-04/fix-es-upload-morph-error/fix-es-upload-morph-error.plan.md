# Plan: fix-es-upload-morph-error

> Created: 2026-04-28
> Status: Draft
> Priority: High (운영 기능 장애)

---

## 1. 문제 정의

### 1-1. 현상

`POST /api/v1/documents/upload-all` 호출 시 Qdrant 저장은 성공하지만
ES 색인이 실패하여 `status: "partial"` 응답 반환.

```json
{
  "es": {
    "index_name": "documents",
    "indexed_count": 0,
    "status": "failed",
    "error": "'str' object has no attribute 'name'"
  },
  "status": "partial"
}
```

### 1-2. 근본 원인 (Root Cause)

**원인 1: kiwipiepy 버전 호환성 깨짐**

- 위치: `src/infrastructure/morph/kiwi_morph_analyzer.py:30`
- 코드: `pos=tok.tag.name`
- 문제: kiwipiepy 0.22.2에서 `tok.tag`는 **문자열**(e.g. `"NNG"`)을 직접 반환.
  이전 버전에서는 enum 객체(`Tag.NNG`)를 반환하여 `.name`으로 문자열 추출이 필요했으나,
  현재 버전에서는 이미 문자열이므로 `.name` 접근 시 `AttributeError` 발생.

**원인 2: _store_to_es에서 에러 로그 누락**

- 위치: `src/application/unified_upload/use_case.py:236-263`
- 문제: `_store_to_es()` 메서드에 try/except 블록이 없음.
  morph_analyzer.analyze()에서 예외 발생 시 `asyncio.gather(return_exceptions=True)`가
  조용히 예외를 캡처하여 `_to_es_result()`에서 문자열로 변환.
  → **어디에서도 `logger.error()`가 호출되지 않아 스택 트레이스 없는 에러 문자열만 응답에 포함**됨.

### 1-3. 영향 범위

| 컴포넌트 | 영향 |
|----------|------|
| ES 색인 | 모든 문서 업로드에서 ES 색인 100% 실패 |
| 하이브리드 검색 | ES 키워드 검색 불가 (벡터 검색만 동작) |
| 운영 모니터링 | 에러 로그 미출력으로 장애 감지 불가 |

---

## 2. 수정 계획

### Task 1: kiwipiepy 호환성 수정

- **파일**: `src/infrastructure/morph/kiwi_morph_analyzer.py`
- **변경**: `tok.tag.name` → `str(tok.tag)` (enum / str 모두 안전하게 처리)
- **테스트**: `tests/infrastructure/morph/test_kiwi_morph_analyzer.py` 에서 실제 tokenize 결과의 tag 타입 검증 추가

### Task 2: _store_to_es 에러 로깅 추가

- **파일**: `src/application/unified_upload/use_case.py`
- **변경**: `_store_to_es()` 내에 try/except 추가하여 예외 발생 시 `logger.error()` 호출 후 re-raise
- **추가**: `execute()` 메서드에서 `asyncio.gather` 결과가 Exception인 경우에도 에러 로그 출력

### Task 3: StructuredLogger exc_info 안정성 개선

- **파일**: `src/infrastructure/logging/structured_logger.py`
- **변경**: `exc_info=exception` → `exc_info=(type(exception), exception, exception.__traceback__)` 변환하여 Python logging 표준 tuple 형식 보장
- **테스트**: 기존 테스트에서 exception 전달 시 스택 트레이스 포함 여부 검증

---

## 3. TDD 순서

```
1. [RED]  KiwiMorphAnalyzer — tok.tag가 문자열일 때 정상 동작 테스트
2. [GREEN] kiwi_morph_analyzer.py — tok.tag.name → str(tok.tag) 수정
3. [RED]  _store_to_es — 예외 발생 시 logger.error 호출 검증 테스트
4. [GREEN] use_case.py — try/except + 에러 로깅 추가
5. [RED]  StructuredLogger — exception 전달 시 exc_info 포맷 검증
6. [GREEN] structured_logger.py — exc_info tuple 변환 적용
7. [REFACTOR] 전체 통합 검증
```

---

## 4. 변경 파일 목록

| 파일 | 변경 유형 |
|------|----------|
| `src/infrastructure/morph/kiwi_morph_analyzer.py` | 수정 (호환성) |
| `src/application/unified_upload/use_case.py` | 수정 (에러 로깅) |
| `src/infrastructure/logging/structured_logger.py` | 수정 (exc_info) |
| `tests/infrastructure/morph/test_kiwi_morph_analyzer.py` | 추가/수정 |
| `tests/application/unified_upload/test_unified_upload_use_case.py` | 추가/수정 |
| `tests/infrastructure/logging/test_structured_logger.py` | 추가/수정 |

---

## 5. 검증 기준

- [ ] KiwiMorphAnalyzer가 kiwipiepy 0.22.2에서 정상 동작
- [ ] `_store_to_es` 실패 시 ERROR 레벨 로그 출력 + 스택 트레이스 포함
- [ ] 업로드 API에서 ES 색인 성공 → `status: "completed"` 반환
- [ ] 기존 하이브리드 검색 정상 동작 확인
