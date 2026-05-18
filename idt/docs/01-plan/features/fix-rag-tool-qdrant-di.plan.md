# Plan: fix-rag-tool-qdrant-di

> RAG Tool Router의 Qdrant DI 설정에서 미정의 변수 참조 버그 수정

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | fix-rag-tool-qdrant-di |
| 작성일 | 2025-05-05 |
| 예상 소요 | 15분 |
| 규모 | Small (1-line 버그 수정) |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | `GET /api/v1/rag-tools/collections` 호출 시 `NameError: name 'qdrant_client' is not defined` 발생, RAG Tool 전체 사용 불가 |
| Solution | `create_app()` 함수 내에서 `qdrant_client` 인스턴스를 생성하여 DI override에 제공 |
| Function UX Effect | RAG Tool Collections API 정상 응답 복구 |
| Core Value | RAG 도구 관리 기능(컬렉션 목록, 검색, 메타데이터 조회) 정상 동작 |

---

## 1. 문제 정의

### 1-1. 현상

```
NameError: name 'qdrant_client' is not defined
```

- **발생 엔드포인트**: `GET /api/v1/rag-tools/collections`
- **발생 위치**: `src/api/main.py:1894`
- **영향 범위**: RAG Tool Router 전체 (collections, search, metadata 등)
- **심각도**: **Critical** — RAG Tool 기능 전면 장애

### 1-2. 근본 원인

`create_app()` 함수(line 1733~) 내 DI override 설정 구간:

```python
# Line 1893-1894
# RAG Tool Router DI
app.dependency_overrides[rag_tool_get_qdrant_client] = lambda: qdrant_client  # ← NameError
```

`qdrant_client` 변수가 `create_app()` 스코프에 정의되지 않음.

다른 팩토리 함수들은 각각 내부에서 `AsyncQdrantClient`를 생성하고 있음:
- `create_collection_factories()` → line 1381에서 로컬 생성
- `create_unified_upload_factories()` → line 1438에서 로컬 생성
- `create_collection_search_factories()` → line 1496에서 로컬 생성

RAG Tool Router DI만 유일하게 팩토리 패턴 없이 직접 변수를 참조하는 구조.

### 1-3. 원인 추정

최근 커밋(`083e4d32`)에서 agent subscription/fork 등의 DI 코드를 추가하면서, 기존에 존재하던 `qdrant_client` 생성 코드가 누락되었거나, 다른 팩토리로 이동되면서 `create_app()` 내의 참조가 끊어진 것으로 판단.

---

## 2. 영향 범위 분석

### 2-1. 직접 영향

| 파일 | 설명 |
|------|------|
| `src/api/main.py:1894` | `qdrant_client` 미정의로 런타임 NameError |
| `src/api/routes/rag_tool_router.py` | DI 플레이스홀더 `get_qdrant_client()`가 override 되지 않아 항상 `NotImplementedError` |

### 2-2. 영향받는 API 엔드포인트

`rag_tool_router`에 정의된 모든 엔드포인트:
- `GET /api/v1/rag-tools/collections`
- `POST /api/v1/rag-tools/search`
- `GET /api/v1/rag-tools/collections/{name}/metadata-keys`

### 2-3. 영향 없는 부분

다른 Qdrant 의존 기능(Collection Management, Unified Upload, Collection Search)은 자체 팩토리 내에서 클라이언트를 생성하므로 정상 동작.

---

## 3. 수정 계획

### Task 1: `create_app()` 내 `qdrant_client` 인스턴스 생성 추가

**위치**: `src/api/main.py`, line 1893 앞

**수정 내용**:
```python
# RAG Tool Router DI
_rag_tool_qdrant = AsyncQdrantClient(
    host=settings.qdrant_host,
    port=settings.qdrant_port,
)
app.dependency_overrides[rag_tool_get_qdrant_client] = lambda: _rag_tool_qdrant
```

**설계 원칙**:
- 다른 팩토리(`create_collection_factories` 등)와 동일한 패턴 유지
- singleton 형태 (앱 수명 동안 하나의 클라이언트 재사용)
- `settings.qdrant_host/port`로 일관된 설정 참조

---

## 4. 리스크 & 제약

| 리스크 | 대응 |
|--------|------|
| 중복 Qdrant 클라이언트 인스턴스 | 추후 공유 인스턴스로 통합 가능하나, 현재는 각 팩토리가 독립 생성하는 기존 패턴 유지 |
| 연결 풀 과다 | AsyncQdrantClient는 lazy connection이므로 인스턴스 수 자체는 문제 없음 |

---

## 5. 완료 기준

- [ ] `GET /api/v1/rag-tools/collections` 호출 시 200 정상 응답
- [ ] NameError 해소 확인
- [ ] 기존 Collection Management / Search 기능에 영향 없음

---

## 6. 예상 작업량

- **규모**: Small (버그 수정)
- **수정 파일**: 1개 (`src/api/main.py`)
- **수정 분량**: 4줄 추가
- **예상 시간**: 5분
