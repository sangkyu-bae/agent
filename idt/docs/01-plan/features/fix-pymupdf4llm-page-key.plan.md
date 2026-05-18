# Plan: fix-pymupdf4llm-page-key

> pymupdf4llm v1.27.2.3 metadata 키 불일치로 인한 PDF 파싱 KeyError 수정

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | fix-pymupdf4llm-page-key |
| 작성일 | 2026-05-15 |
| 예상 소요 | 10분 |
| 규모 | Small (1-line 버그 수정) |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | `POST /api/v1/preview/parse`로 PDF 업로드 시 `KeyError: 'page'` 발생, PDF 프리뷰 파싱 전면 불가 |
| Solution | pymupdf4llm v1.27.2.3의 실제 metadata 키(`page_number`)로 접근 코드 수정 |
| Function UX Effect | PDF 업로드 → Markdown 프리뷰 변환 정상 동작 복구 |
| Core Value | 문서 파싱 파이프라인 안정성 확보, PDF 프리뷰 기능 정상화 |

---

## 1. 문제 정의

### 1-1. 현상

```
KeyError: 'page'
```

- **발생 엔드포인트**: `POST /api/v1/preview/parse`
- **발생 위치**: `src/infrastructure/parser/pymupdf4llm_parser.py:105`
- **영향 범위**: PyMuPDF4LLM 파서를 사용하는 모든 PDF 파싱 (preview, ingest)
- **심각도**: **Critical** — PDF 프리뷰/파싱 전면 장애

### 1-2. 근본 원인

`pymupdf4llm.to_markdown(page_chunks=True)` 반환값의 metadata 구조 변경:

```python
# 코드가 기대하는 키 (존재하지 않음)
chunk["metadata"]["page"]

# pymupdf4llm v1.27.2.3 실제 반환 키
chunk["metadata"]["page_number"]  # 1-based integer
```

**실제 metadata 구조** (v1.27.2.3):
```python
{
    'format': 'PDF 1.7',
    'title': '', 'author': '', 'subject': '', 'keywords': '',
    'creator': '', 'producer': '',
    'creationDate': '', 'modDate': '',
    'trapped': '', 'encryption': None,
    'file_path': '',
    'page_count': 1,
    'page_number': 1   # ← 이 키를 사용해야 함 (1-based)
}
```

기존 코드는 `chunk["metadata"]["page"]`에 +1을 하여 1-based로 변환했으나,
v1.27.2.3에서는 이미 `page_number`가 1-based로 제공됨.

---

## 2. 수정 계획

### 2-1. 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/infrastructure/parser/pymupdf4llm_parser.py:105` | `chunk["metadata"]["page"] + 1` → `chunk["metadata"]["page_number"]` |

### 2-2. 변경 상세

**Before (line 105)**:
```python
page_num = chunk["metadata"]["page"] + 1
```

**After**:
```python
page_num = chunk["metadata"]["page_number"]
```

- `page_number`는 이미 1-based이므로 `+1` 불필요
- `.get()` 방어 코드 불필요 — `page_chunks=True`일 때 `page_number`는 항상 존재

### 2-3. 영향 범위

- `_convert_to_documents()` 메서드 내부만 변경
- `parse()`, `parse_bytes()` 호출 경로 모두 동일 메서드 사용 → 자동 수정
- downstream (`DocumentMetadata.page`, `preview_router`) — 동일한 1-based int 전달, 영향 없음

---

## 3. 검증 계획

- [ ] `POST /api/v1/preview/parse`로 PDF 업로드 → 200 응답, pages 배열 반환 확인
- [ ] 다중 페이지 PDF → page 번호 순차 증가 확인 (1, 2, 3, ...)
- [ ] 빈 페이지 포함 PDF → 빈 페이지 스킵, 나머지 page 번호 정확 확인

---

## 4. 리스크

| 리스크 | 대응 |
|--------|------|
| pymupdf4llm 향후 버전에서 키 이름 재변경 | pyproject.toml에 버전 고정 확인 |
| 다른 파서에서 동일 메서드 사용 | PyMuPDF4LLMParser만 해당, 다른 파서 영향 없음 |
