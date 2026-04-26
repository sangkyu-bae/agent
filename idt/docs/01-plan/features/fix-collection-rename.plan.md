# fix-collection-rename Planning Document

> **Summary**: 컬렉션 이름 수정(PATCH /api/v1/collections/{name}) 요청 시 실제 이름이 변경되지 않는 버그 수정
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-22
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

`PATCH /api/v1/collections/{name}` 엔드포인트로 컬렉션 이름을 변경하면 API는 200 OK를 반환하지만,
실제로 컬렉션 목록에서 이름이 변경되지 않는 버그를 수정한다.

### 1.2 Background

**재현 로그:**
```
request_id : f007f120-6492-4c91-90f4-2b00a2620ebb
method     : PATCH
endpoint   : /api/v1/collections/manual
body       : {'new_name': 'manual2'}
```

API는 성공 응답을 반환하지만 컬렉션 목록 조회 시 여전히 원래 이름(`manual`)으로 표시된다.

### 1.3 Root Cause Analysis

현재 코드 흐름과 문제점:

```
Router (collection_router.py:247)
  → UseCase.rename_collection (use_case.py:109)
    → repo.collection_exists(old_name)       ← Qdrant 실제 컬렉션만 확인
    → repo.update_collection_alias(old_name, new_name)
      → Qdrant CreateAliasOperation          ← 새 alias만 생성, 이전 alias 미삭제
```

**근본 원인 3가지:**

| # | 원인 | 위치 | 설명 |
|---|------|------|------|
| 1 | Alias만 생성, 이전 alias 미삭제 | `qdrant_collection_repository.py:59-71` | `CreateAliasOperation`만 수행하고 기존 alias에 대한 `DeleteAliasOperation` 없음 |
| 2 | list_collections에 alias 미반영 | `qdrant_collection_repository.py:15-28` | 실제 Qdrant 컬렉션 이름만 반환하므로 alias 변경이 목록에 나타나지 않음 |
| 3 | alias 매핑 미저장 | `rag_tool_router.py:37-38` | `get_collection_aliases()`가 빈 dict 반환, main.py에서 override 없음 |

### 1.4 Related Documents

- Router: `src/api/routes/collection_router.py:247-267`
- UseCase: `src/application/collection/use_case.py:109-126`
- Repository: `src/infrastructure/collection/qdrant_collection_repository.py:59-71`
- Interface: `src/domain/collection/interfaces.py:30`

---

## 2. Scope

### 2.1 In Scope

- [x] Qdrant alias 생성 시 이전 alias 삭제 로직 추가
- [x] `list_collections` 응답에 alias 정보 반영
- [x] `collection_exists` 검사 시 alias도 포함하여 확인
- [x] 기존 테스트 수정 및 신규 테스트 추가

### 2.2 Out of Scope

- Qdrant 컬렉션 자체 이름 변경 (Qdrant는 컬렉션 rename을 지원하지 않으므로 alias 기반으로 해결)
- MySQL에 별도 alias 매핑 테이블 신규 생성
- 프론트엔드 UI 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | rename 시 이전 alias 삭제 + 새 alias 생성을 하나의 operation으로 수행 | High | Pending |
| FR-02 | `list_collections`에서 alias가 있는 컬렉션은 alias 이름으로 표시 | High | Pending |
| FR-03 | rename 대상이 alias인 경우에도 정상 동작 (alias → alias 변경) | Medium | Pending |
| FR-04 | rename 후 기존 이름으로 접근 시 적절한 에러 반환 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | rename 응답 시간 < 500ms | API 로그 |
| Reliability | 기존 컬렉션 데이터 무손실 | 테스트 검증 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] `PATCH /api/v1/collections/{name}` 호출 후 `GET /api/v1/collections`에서 변경된 이름 확인
- [x] 이전 이름(alias)으로 접근 불가 확인
- [x] 단위 테스트 작성 및 통과
- [x] 기존 테스트 깨지지 않음

### 4.2 Quality Criteria

- [x] TDD 방식 (테스트 먼저 작성)
- [x] DDD 레이어 규칙 준수
- [x] Zero lint error

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Qdrant alias API 동작이 버전별로 다를 수 있음 | Medium | Low | qdrant-client 문서 확인, 기존 버전 유지 |
| 기존 alias가 있는 컬렉션의 데이터 접근 경로 변경 | High | Medium | RAG/검색 경로에서 alias resolve 로직 확인 |
| rename 중 동시 요청으로 인한 race condition | Low | Low | Qdrant atomic alias operation 사용 |

---

## 6. Architecture Considerations

### 6.1 Project Level

- **Level**: Enterprise (Thin DDD)
- 기존 아키텍처 유지, 레이어 규칙 준수

### 6.2 Fix Strategy

**접근 방식: Qdrant Alias 기반 rename 보완**

Qdrant는 컬렉션 rename을 지원하지 않으므로 alias를 활용한다.
현재 `CreateAliasOperation`만 사용 중인 것을 `DeleteAliasOperation` + `CreateAliasOperation`으로 보완한다.

```
수정 전:
  update_collection_aliases([CreateAlias(collection=old, alias=new)])

수정 후:
  update_collection_aliases([
      DeleteAlias(alias=old),        ← 기존 alias 제거 (alias인 경우)
      CreateAlias(collection=실제컬렉션, alias=new)  ← 새 alias 생성
  ])
```

### 6.3 영향 받는 파일

| Layer | File | 변경 내용 |
|-------|------|----------|
| Infrastructure | `qdrant_collection_repository.py` | `update_collection_alias` 로직 수정, alias 조회 메서드 추가 |
| Application | `use_case.py` | rename 로직에서 실제 컬렉션 이름 resolve |
| Domain | `interfaces.py` | 필요 시 인터페이스 시그니처 조정 |
| Test | `tests/` | 관련 테스트 추가 |

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` coding conventions 확인
- [x] DDD 레이어 규칙 확인
- [x] TDD 필수 규칙 확인

### 7.2 Conventions to Follow

| Category | Rule |
|----------|------|
| Layer | domain → infrastructure 참조 금지 |
| Error | `print()` 사용 금지, logger 사용 |
| Transaction | Repository 내부에서 commit/rollback 금지 |
| Test | 테스트 먼저 작성 (Red → Green → Refactor) |

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`fix-collection-rename.design.md`)
2. [ ] TDD로 구현
3. [ ] Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft | AI Assistant |
