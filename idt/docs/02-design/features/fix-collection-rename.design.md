# fix-collection-rename Design Document

> **Summary**: 컬렉션 rename 시 alias만 생성하고 이전 alias를 삭제하지 않아 이름이 변경되지 않는 버그 수정
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-22
> **Status**: Draft
> **Planning Doc**: [fix-collection-rename.plan.md](../01-plan/features/fix-collection-rename.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- Qdrant alias 기반 rename이 실제로 동작하도록 수정
- `list_collections`에서 alias가 반영된 이름 반환
- `collection_exists` 검사 시 alias도 인식
- 기존 API 계약(request/response) 변경 없이 내부 로직만 수정

### 1.2 Design Principles

- 최소 변경 원칙: 버그 원인 3가지만 정확히 수정
- DDD 레이어 규칙 준수: domain에 인터페이스 추가, infrastructure에서 구현
- Qdrant atomic alias operation 활용으로 race condition 방지

---

## 2. Architecture

### 2.1 현재 문제점 (Before)

```
PATCH /collections/{name}  (body: {new_name})
  │
  ├─ UseCase.rename_collection(old_name, new_name)
  │    ├─ repo.collection_exists(old_name)        ← 실제 컬렉션만 확인, alias 미인식
  │    └─ repo.update_collection_alias(old, new)
  │         └─ CreateAlias(collection=old, alias=new)  ← 이전 alias 미삭제
  │
  └─ GET /collections
       └─ repo.list_collections()
            └─ get_collections()  ← 실제 컬렉션 이름만 반환, alias 미반영
```

### 2.2 수정 후 (After)

```
PATCH /collections/{name}  (body: {new_name})
  │
  ├─ UseCase.rename_collection(old_name, new_name)
  │    ├─ repo.collection_exists(old_name)        ← 실제 컬렉션 + alias 모두 확인
  │    └─ repo.update_collection_alias(old, new)
  │         ├─ get_all_aliases()                   ← alias 매핑 조회
  │         ├─ resolve actual collection name      ← old가 alias면 실제 이름 resolve
  │         ├─ DeleteAlias(alias=old)              ← 기존 alias 삭제 (alias인 경우)
  │         └─ CreateAlias(collection=실제, alias=new)  ← 새 alias 생성
  │
  └─ GET /collections
       └─ repo.list_collections()
            ├─ get_collections()                   ← 실제 컬렉션 목록
            ├─ get_all_aliases()                   ← alias 매핑 조회
            └─ alias가 있으면 alias 이름으로 표시  ← alias 반영
```

### 2.3 Data Flow

```
rename 요청:
  User Input → Router → UseCase → Repository
                                    ├─ get_all_aliases()        → Qdrant
                                    ├─ resolve actual name
                                    └─ update_collection_aliases([Delete, Create]) → Qdrant (atomic)

list 요청:
  User Input → Router → UseCase → Repository
                                    ├─ get_collections()        → Qdrant
                                    ├─ get_all_aliases()        → Qdrant
                                    └─ merge (alias 우선 표시)  → Response
```

---

## 3. Layer-by-Layer Changes

### 3.1 Domain Layer (`src/domain/collection/`)

**`interfaces.py`** — `CollectionRepositoryInterface`에 메서드 2개 추가:

```python
@abstractmethod
async def get_all_aliases(self) -> dict[str, str]:
    """모든 alias 매핑 반환. Returns {alias_name: collection_name}."""
    ...

@abstractmethod
async def resolve_collection_name(self, name: str) -> str:
    """alias면 실제 컬렉션 이름 반환, 아니면 name 그대로 반환."""
    ...
```

변경 없는 항목:
- `schemas.py`: `CollectionInfo`, `CollectionDetail` 등 기존 스키마 변경 없음
- `policy.py`: 기존 정책 로직 변경 없음

### 3.2 Infrastructure Layer (`src/infrastructure/collection/`)

**`qdrant_collection_repository.py`** — 메서드 4개 수정, 2개 추가:

#### 신규: `get_all_aliases()`

```python
async def get_all_aliases(self) -> dict[str, str]:
    result = await self._client.get_aliases()
    return {
        alias.alias_name: alias.collection_name
        for alias in result.aliases
    }
```

#### 신규: `resolve_collection_name()`

```python
async def resolve_collection_name(self, name: str) -> str:
    aliases = await self.get_all_aliases()
    return aliases.get(name, name)
```

#### 수정: `list_collections()` — alias 반영

```python
async def list_collections(self) -> list[CollectionInfo]:
    result = await self._client.get_collections()
    aliases = await self.get_all_aliases()
    # reverse map: actual_collection_name → alias_name
    alias_reverse = {v: k for k, v in aliases.items()}

    infos: list[CollectionInfo] = []
    for c in result.collections:
        detail = await self._client.get_collection(c.name)
        display_name = alias_reverse.get(c.name, c.name)
        infos.append(
            CollectionInfo(
                name=display_name,
                vectors_count=detail.indexed_vectors_count or 0,
                points_count=detail.points_count or 0,
                status=detail.status.value if detail.status else "unknown",
            )
        )
    return infos
```

#### 수정: `collection_exists()` — alias 포함 확인

```python
async def collection_exists(self, name: str) -> bool:
    if await self._client.collection_exists(name):
        return True
    aliases = await self.get_all_aliases()
    return name in aliases
```

#### 수정: `update_collection_alias()` — Delete + Create atomic

```python
async def update_collection_alias(
    self, old_name: str, new_alias: str
) -> None:
    aliases = await self.get_all_aliases()
    actual_collection = aliases.get(old_name, old_name)

    operations: list = []
    if old_name in aliases:
        operations.append(
            models.DeleteAliasOperation(
                delete_alias=models.DeleteAlias(alias_name=old_name)
            )
        )
    operations.append(
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name=actual_collection,
                alias_name=new_alias,
            )
        )
    )
    await self._client.update_collection_aliases(
        change_aliases_operations=operations
    )
```

#### 수정: `get_collection()` — alias resolve 추가

```python
async def get_collection(self, name: str) -> CollectionDetail | None:
    actual_name = await self.resolve_collection_name(name)
    if not await self._client.collection_exists(actual_name):
        return None
    detail = await self._client.get_collection(actual_name)
    params = detail.config.params
    return CollectionDetail(
        name=name,  # 요청한 이름(alias 포함) 그대로 반환
        vectors_count=detail.indexed_vectors_count or 0,
        points_count=detail.points_count or 0,
        status=detail.status.value if detail.status else "unknown",
        vector_size=params.vectors.size,
        distance=params.vectors.distance.value,
    )
```

### 3.3 Application Layer (`src/application/collection/`)

**`use_case.py`** — `rename_collection` 변경 없음

현재 `rename_collection`은 `repo.collection_exists(old_name)` → `repo.update_collection_alias(old_name, new_name)` 순서로 호출한다.
`collection_exists`와 `update_collection_alias` 모두 infrastructure에서 alias를 인식하도록 수정되므로 UseCase 코드 변경은 불필요하다.

### 3.4 Interface Layer (`src/api/routes/`)

**변경 없음** — Router의 request/response 스키마, 에러 처리 로직은 그대로 유지.

---

## 4. API Specification

### 기존 API 계약 유지 (변경 없음)

#### `PATCH /api/v1/collections/{name}`

**Request:**
```json
{ "new_name": "manual2" }
```

**Response (200):**
```json
{
  "old_name": "manual",
  "new_name": "manual2",
  "message": "Collection alias updated successfully"
}
```

#### `GET /api/v1/collections`

**Response (200) — 수정 후 동작 변경:**
```json
{
  "collections": [
    {
      "name": "manual2",       // Before fix: "manual" (alias 미반영)
      "vectors_count": 100,
      "points_count": 100,
      "status": "green"
    }
  ]
}
```

---

## 5. Error Handling

### 5.1 에러 시나리오

| 시나리오 | 현재 동작 | 수정 후 동작 |
|----------|----------|-------------|
| 존재하지 않는 컬렉션 rename | 404 (실제 컬렉션만 확인) | 404 (실제 + alias 모두 확인) |
| alias → alias rename (manual2 → manual3) | alias 중복 생성 | 이전 alias 삭제 + 새 alias 생성 |
| 이미 존재하는 이름으로 rename | 검증 없음 | 추후 개선 대상 (현 scope 외) |

### 5.2 에러 응답 형식 (변경 없음)

```json
{
  "detail": "Collection 'nonexistent' not found"
}
```

---

## 6. Test Plan

### 6.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `QdrantCollectionRepository` 메서드 6개 | pytest + AsyncMock |
| Unit Test | `CollectionManagementUseCase.rename_collection` | pytest + Mock |

### 6.2 Infrastructure Test Cases (`test_qdrant_collection_repository.py`)

#### `TestGetAllAliases`
- [ ] alias가 없을 때 빈 dict 반환
- [ ] alias가 있을 때 `{alias_name: collection_name}` 반환

#### `TestResolveCollectionName`
- [ ] alias인 경우 실제 컬렉션 이름 반환
- [ ] 실제 컬렉션 이름인 경우 그대로 반환

#### `TestListCollections` (기존 수정)
- [ ] alias가 없는 컬렉션은 실제 이름 반환
- [ ] alias가 있는 컬렉션은 alias 이름으로 반환

#### `TestCollectionExists` (기존 수정)
- [ ] 실제 컬렉션 이름으로 True
- [ ] alias 이름으로 True
- [ ] 존재하지 않는 이름으로 False

#### `TestUpdateCollectionAlias` (기존 수정)
- [ ] 실제 컬렉션 → alias 생성: CreateAlias만 실행
- [ ] 기존 alias → 새 alias 변경: DeleteAlias + CreateAlias 실행
- [ ] atomic operation (하나의 `update_collection_aliases` 호출)

#### `TestGetCollection` (기존 수정)
- [ ] alias 이름으로 조회 시 정상 반환 (name 필드에 alias 표시)
- [ ] 존재하지 않는 이름으로 None 반환

---

## 7. Implementation Order

### 7.1 TDD 순서 (Red → Green → Refactor)

```
Step 1: Domain — 인터페이스 추가
  ├─ interfaces.py: get_all_aliases, resolve_collection_name 추가
  └─ 테스트 불필요 (추상 메서드)

Step 2: Infrastructure — 신규 메서드 (TDD)
  ├─ RED:   test_get_all_aliases, test_resolve_collection_name 작성
  ├─ GREEN: get_all_aliases, resolve_collection_name 구현
  └─ REFACTOR: 중복 제거

Step 3: Infrastructure — 기존 메서드 수정 (TDD)
  ├─ RED:   list_collections alias 반영 테스트, collection_exists alias 테스트
  ├─ GREEN: list_collections, collection_exists 수정
  └─ REFACTOR

Step 4: Infrastructure — rename 핵심 수정 (TDD)
  ├─ RED:   update_collection_alias Delete+Create 테스트
  ├─ GREEN: update_collection_alias 수정
  └─ REFACTOR

Step 5: Infrastructure — get_collection alias resolve (TDD)
  ├─ RED:   get_collection alias 조회 테스트
  ├─ GREEN: get_collection 수정
  └─ REFACTOR

Step 6: 통합 검증
  └─ 기존 테스트 전체 통과 확인
```

### 7.2 파일 변경 요약

| # | File | Change | Lines |
|---|------|--------|-------|
| 1 | `src/domain/collection/interfaces.py` | 추상 메서드 2개 추가 | ~8 |
| 2 | `src/infrastructure/collection/qdrant_collection_repository.py` | 메서드 2개 추가, 4개 수정 | ~40 |
| 3 | `tests/infrastructure/collection/test_qdrant_collection_repository.py` | 테스트 케이스 ~10개 추가/수정 | ~80 |

---

## 8. Dependency & Risk

### 8.1 Qdrant Client API 의존성

| API | 용도 | qdrant-client 버전 |
|-----|------|-------------------|
| `client.get_aliases()` | 전체 alias 목록 조회 | >= 1.7.0 |
| `models.DeleteAliasOperation` | alias 삭제 | >= 1.7.0 |
| `models.CreateAliasOperation` | alias 생성 (기존 사용 중) | >= 1.7.0 |

### 8.2 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| `get_all_aliases()` 호출 추가로 인한 성능 | alias 수가 적으므로 무시 가능 수준. 필요 시 캐싱 고려 |
| 복수 alias가 하나의 컬렉션을 가리키는 경우 | `alias_reverse` 맵에서 마지막 항목이 우선. 현재 1:1 매핑만 사용하므로 문제 없음 |
| alias 이름과 실제 컬렉션 이름이 충돌 | Qdrant가 자체적으로 충돌 방지. 별도 처리 불필요 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft | AI Assistant |
