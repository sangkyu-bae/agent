# Plan: fix-qdrant-vectors-count

> qdrant-client 버전 업그레이드로 인한 CollectionInfo 속성 호환성 오류 수정

---

## 1. 배경 (Background)

### 1-1. 현상

`GET /api/v1/collections` 호출 시 500 에러 발생:

```
AttributeError: 'CollectionInfo' object has no attribute 'vectors_count'
```

- 발생 위치: `qdrant_collection_repository.py:23`
- 영향 범위: `list_collections()`, `get_collection()` 두 메서드 모두 동일 문제

### 1-2. 원인 분석

| 항목 | 내용 |
|------|------|
| 현재 qdrant-client 버전 | **1.16.2** |
| 문제 속성 | `CollectionInfo.vectors_count` — **삭제됨** |
| 대체 속성 | `CollectionInfo.indexed_vectors_count` — 사용 가능 |
| 사용 가능 필드 | `status`, `optimizer_status`, `warnings`, `indexed_vectors_count`, `points_count`, `segments_count`, `config`, `payload_schema` |

qdrant-client가 v1.12+ 이후 `vectors_count` 필드를 deprecated → 제거했으며,
`indexed_vectors_count`가 인덱싱된 벡터 수를 나타내는 대체 필드이다.

### 1-3. 영향 범위

- `src/infrastructure/collection/qdrant_collection_repository.py` — **직접 원인** (23행, 37행)
- `src/domain/collection/schemas.py` — domain 스키마에 `vectors_count` 필드 존재 (변경 불필요, 내부 VO 이름은 유지 가능)
- 프론트엔드 — API 응답 스키마가 바뀌지 않으므로 영향 없음

---

## 2. 수정 계획

### 2-1. 수정 대상 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/infrastructure/collection/qdrant_collection_repository.py` | `detail.vectors_count` → `detail.indexed_vectors_count` (23행, 37행) |

### 2-2. 변경하지 않는 것

- **domain 스키마** (`CollectionInfo.vectors_count` 필드명): 도메인 VO는 외부 라이브러리와 독립적으로 유지. infrastructure 어댑터에서 매핑만 변경.
- **API 응답 스키마**: 프론트엔드 영향 없도록 응답 필드명 유지.

### 2-3. 테스트 계획

1. 기존 collection 관련 테스트가 있으면 실행하여 통과 확인
2. `GET /api/v1/collections` 수동 호출로 정상 응답 확인

---

## 3. 리스크

| 리스크 | 대응 |
|--------|------|
| `indexed_vectors_count`와 기존 `vectors_count`의 의미 차이 | indexed_vectors_count는 인덱싱 완료된 벡터만 카운트. 실시간 insert 직후엔 수치가 다를 수 있으나 UI 표시 용도로는 충분 |
| 향후 qdrant-client 추가 변경 | `points_count`는 안정적 필드이므로 벡터 수 대신 포인트 수를 주 지표로 사용하는 것도 고려 가능 |

---

## 4. 예상 작업 시간

5분 이내 (단순 속성명 매핑 변경)
