# Design: fix-es-upload-morph-error

> Created: 2026-04-28
> Plan: `docs/01-plan/features/fix-es-upload-morph-error.plan.md`
> Status: Draft

---

## 1. 변경 대상 및 현재 코드 분석

### 1-1. KiwiMorphAnalyzer (근본 원인)

**현재 코드** (`src/infrastructure/morph/kiwi_morph_analyzer.py:26-34`):

```python
raw_tokens = self._kiwi.tokenize(text)
tokens = tuple(
    MorphToken(
        surface=tok.form,
        pos=tok.tag.name,   # ← BUG: kiwipiepy 0.22.2에서 tok.tag는 이미 str
        start=tok.start,
        length=tok.len,
    )
    for tok in raw_tokens
)
```

**원인**: kiwipiepy 이전 버전에서 `tok.tag`는 `Tag` enum 객체(`Tag.NNG`)를 반환하여
`.name` 속성으로 문자열 추출이 필요했음. 0.22.2에서는 이미 `str`을 반환하므로 `AttributeError` 발생.

### 1-2. UnifiedUploadUseCase._store_to_es (에러 로깅 누락)

**현재 코드** (`src/application/unified_upload/use_case.py:236-263`):

```python
async def _store_to_es(self, chunks, document_id, request, request_id) -> EsStoreResult:
    es_docs = []
    for chunk in chunks:
        morph_result = self._morph_analyzer.analyze(chunk.page_content)  # ← 여기서 예외 발생
        # ... 이하 실행 안 됨
    count = await self._es_repo.bulk_index(es_docs, request_id)
    return EsStoreResult(indexed_count=count)
```

**문제**: try/except 없이 예외가 `asyncio.gather(return_exceptions=True)`로 조용히 캡처됨.
`_to_es_result()`에서 `str(exception)`으로 변환되어 응답에 포함되지만 **로그는 미출력**.

### 1-3. StructuredLogger._log (exc_info 방어 코드 부재)

**현재 코드** (`src/infrastructure/logging/structured_logger.py:128-131`):

```python
if exception is not None:
    self._logger.log(
        level, message, exc_info=exception, extra=extra, stacklevel=3
    )
```

**분석**: Python 3에서 `exc_info=exception`은 동작하나, `__traceback__`이 `None`인 예외
(raise 없이 생성된 경우)에서 스택 트레이스 누락 가능.
`StructuredFormatter:67`에서 `traceback.format_exception(*record.exc_info)` 호출 시
`(type, value, None)` 형태가 되어 트레이스 없는 불완전한 로그 출력.

---

## 2. 변경 설계

### 2-1. Task 1: KiwiMorphAnalyzer 호환성 수정

**파일**: `src/infrastructure/morph/kiwi_morph_analyzer.py`

**변경 전**:
```python
pos=tok.tag.name,
```

**변경 후**:
```python
pos=tok.tag if isinstance(tok.tag, str) else tok.tag.name,
```

**이유**: `str(tok.tag)`도 가능하지만, enum의 `__str__`이 `"Tag.NNG"` 형태를 반환할 수 있어
명시적 분기가 안전함. 향후 kiwipiepy 버전 변경에도 대응 가능.

**테스트 추가** (`tests/infrastructure/morph/test_kiwi_morph_analyzer.py`):

```python
def test_analyze_handles_string_tag(self, mock_kiwi_cls):
    """kiwipiepy 0.22+ 에서 tok.tag가 str인 경우 정상 동작."""
    token = SimpleNamespace(form="금융", tag="NNG", start=0, len=2)
    mock_kiwi_cls.return_value.tokenize.return_value = [token]
    analyzer = KiwiMorphAnalyzer()
    result = analyzer.analyze("금융")
    assert result.tokens[0].pos == "NNG"
```

---

### 2-2. Task 2: _store_to_es 에러 로깅 추가

**파일**: `src/application/unified_upload/use_case.py`

**설계 원칙**: 
- `_store_to_es` 내부에 try/except 추가 → `logger.error()` 호출 후 re-raise
- `execute()`에서 `asyncio.gather` 결과 중 Exception을 감지하여 추가 로그 출력 (이중 안전망)

**변경 1 — `_store_to_es` 메서드**:

```python
async def _store_to_es(
    self, chunks, document_id, request, request_id
) -> EsStoreResult:
    try:
        es_docs = []
        for chunk in chunks:
            morph_result = self._morph_analyzer.analyze(chunk.page_content)
            morph_keywords = self._extract_morph_keywords(morph_result)
            morph_text = " ".join(morph_keywords)
            # ... 기존 body 구성 로직 동일 ...
            es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))

        count = await self._es_repo.bulk_index(es_docs, request_id)
        return EsStoreResult(indexed_count=count)
    except Exception as e:
        self._logger.error(
            "ES store failed",
            exception=e,
            request_id=request_id,
            document_id=document_id,
            collection_name=request.collection_name,
        )
        raise
```

**변경 2 — `execute` 메서드 gather 결과 로깅**:

```python
qdrant_raw, es_raw = await asyncio.gather(
    self._store_to_qdrant(chunks, embedding_model, request, request_id),
    self._store_to_es(chunks, document_id, request, request_id),
    return_exceptions=True,
)

if isinstance(qdrant_raw, Exception):
    self._logger.error(
        "Qdrant store failed in gather",
        exception=qdrant_raw,
        request_id=request_id,
    )
if isinstance(es_raw, Exception):
    self._logger.error(
        "ES store failed in gather",
        exception=es_raw,
        request_id=request_id,
    )
```

**테스트 추가** (`tests/application/unified_upload/test_use_case.py`):

```python
async def test_execute_es_fails_logs_error(self):
    """ES 저장 실패 시 logger.error가 호출된다."""
    # morph_analyzer.analyze.side_effect = RuntimeError("morph fail")
    # → result.es.error is not None
    # → deps["logger"].error.assert_called()
```

---

### 2-3. Task 3: StructuredLogger exc_info 안정성 개선

**파일**: `src/infrastructure/logging/structured_logger.py`

**변경 전**:
```python
if exception is not None:
    self._logger.log(
        level, message, exc_info=exception, extra=extra, stacklevel=3
    )
```

**변경 후**:
```python
if exception is not None:
    exc_info = (type(exception), exception, exception.__traceback__)
    self._logger.log(
        level, message, exc_info=exc_info, extra=extra, stacklevel=3
    )
```

**이유**: Python logging 모듈은 내부적으로 `isinstance(exc_info, BaseException)` 분기로
tuple 변환하지만, 명시적 tuple 전달이 `StructuredFormatter.format()`과의 계약을 확실히 보장.
`__traceback__`이 `None`이어도 `traceback.format_exception`은 정상 동작.

**테스트 추가** (`tests/infrastructure/logging/test_structured_logger.py`):

```python
def test_error_with_no_traceback_exception_does_not_crash(self, logger):
    """raise 없이 생성된 예외도 안전하게 로깅된다."""
    structured_logger, stream = logger
    exc = ValueError("no traceback")  # raise하지 않아 __traceback__ is None
    structured_logger.error("Error occurred", exception=exc)
    output = stream.getvalue()
    parsed = json.loads(output.split("\n")[0])
    assert parsed["error_type"] == "ValueError"
    assert parsed["error_message"] == "no traceback"
```

---

## 3. 구현 순서 (TDD)

```
Step 1 ─ KiwiMorphAnalyzer 호환성
  [RED]   test_analyze_handles_string_tag 추가 → 실패 확인
  [GREEN] kiwi_morph_analyzer.py 수정 → 통과 확인

Step 2 ─ _store_to_es 에러 로깅
  [RED]   test_execute_es_fails_logs_error 추가 → 실패 확인
  [GREEN] use_case.py에 try/except + gather 결과 로깅 추가 → 통과 확인

Step 3 ─ StructuredLogger exc_info
  [RED]   test_error_with_no_traceback_exception_does_not_crash 추가 → 실패 확인
  [GREEN] structured_logger.py exc_info tuple 변환 → 통과 확인

Step 4 ─ 전체 회귀 테스트
  pytest tests/ 전체 실행 → 기존 테스트 통과 확인
```

---

## 4. 변경 파일 요약

| 파일 | 변경 유형 | 레이어 |
|------|----------|--------|
| `src/infrastructure/morph/kiwi_morph_analyzer.py` | 수정 (1줄) | infrastructure |
| `src/application/unified_upload/use_case.py` | 수정 (try/except + gather 로깅) | application |
| `src/infrastructure/logging/structured_logger.py` | 수정 (exc_info 변환) | infrastructure |
| `tests/infrastructure/morph/test_kiwi_morph_analyzer.py` | 테스트 추가 (1건) | test |
| `tests/application/unified_upload/test_use_case.py` | 테스트 추가 (1건) | test |
| `tests/infrastructure/logging/test_structured_logger.py` | 테스트 추가 (1건) | test |

---

## 5. 아키텍처 영향도

- **레이어 규칙 위반 없음**: 모든 변경이 해당 레이어 내에서 완결
- **인터페이스 변경 없음**: `LoggerInterface`, `MorphAnalyzerInterface` 시그니처 불변
- **API 계약 변경 없음**: 응답 스키마 `UnifiedUploadResponse` 동일 (error 필드 값만 달라짐)
- **하위 호환성**: `tok.tag`가 enum인 이전 kiwipiepy 버전에서도 동작

---

## 6. 검증 기준

| # | 검증 항목 | 기대 결과 |
|---|----------|----------|
| V1 | kiwipiepy 0.22.2에서 MorphAnalyzer 정상 동작 | pos가 "NNG", "VV" 등 문자열로 정상 추출 |
| V2 | _store_to_es 실패 시 ERROR 로그 출력 | logger.error 호출 + 스택 트레이스 포함 |
| V3 | upload-all API에서 ES 색인 성공 | status: "completed", indexed_count > 0 |
| V4 | __traceback__ 없는 예외 로깅 | 크래시 없이 error_type, error_message 출력 |
| V5 | 기존 테스트 전체 통과 | pytest 회귀 없음 |
