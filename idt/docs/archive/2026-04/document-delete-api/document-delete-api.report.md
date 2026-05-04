# PDCA Completion Report: document-delete-api

> **Feature**: 컬렉션 내 문서 삭제 API (Qdrant + ES + MySQL 3중 동기 삭제)
> **Task ID**: DOC-DELETE-001
> **Date**: 2026-04-29
> **Status**: Completed
> **Match Rate**: 95% -> 98% (Gap 수정 후)

---

## 1. PDCA Cycle Summary

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ 98% → [Report] ✅
```

| Phase | 산출물 | 상태 |
|-------|--------|------|
| Plan | `docs/01-plan/features/document-delete-api.plan.md` | ✅ |
| Design | `docs/02-design/features/document-delete-api.design.md` | ✅ |
| Do | 구현 코드 + 테스트 | ✅ |
| Check | Gap Analysis (95% → 98%) | ✅ |
| Report | 본 문서 | ✅ |

---

## 2. Feature Overview

### 목적

컬렉션에 업로드된 문서의 청크 데이터와 메타데이터를 삭제하는 API.
Qdrant(벡터) + Elasticsearch(BM25) + MySQL(메타데이터) 3개 저장소를 동기 삭제한다.

### API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| DELETE | `/api/v1/collections/{collection_name}/documents/{document_id}` | 단건 삭제 |
| DELETE | `/api/v1/collections/{collection_name}/documents` | 일괄 삭제 (body: `document_ids`) |

### 삭제 흐름

```
권한 확인 → Qdrant 청크 삭제 → ES 청크 삭제 → MySQL 메타데이터 삭제 → Activity Log
```

### 권한 모델

| 조건 | 삭제 허용 |
|------|----------|
| 문서 업로더 본인 (`metadata.user_id == user_id`) | ✅ |
| 컬렉션 소유자 (`permission.owner_id == user_id`) | ✅ |
| ADMIN 역할 (`X-User-Role: admin`) | ✅ |
| 그 외 | ❌ 403 |

---

## 3. Implementation Summary

### 신규 파일

| 파일 | 레이어 | 줄 수 | 설명 |
|------|--------|-------|------|
| `src/domain/doc_browse/policies.py` | Domain | 27 | 문서 삭제 권한 Policy (순수 판단 로직) |
| `src/application/doc_browse/delete_document_use_case.py` | Application | ~230 | 단건/일괄 삭제 UseCase + Qdrant/ES/MySQL 삭제 |

### 수정 파일

| 파일 | 레이어 | 변경 내용 |
|------|--------|----------|
| `src/domain/doc_browse/schemas.py` | Domain | `DeleteDocumentResult` dataclass 추가 |
| `src/api/routes/doc_browse_router.py` | Interface | DELETE 엔드포인트 2개 + 스키마 4개 + DI placeholder |
| `src/api/main.py` | DI | `_delete_document_uc_factory` 추가 (per-request DI) |
| `docs/task-registry.md` | Docs | DOC-DELETE-001 등록 |

### 기존 인프라 재사용 (변경 없음)

| 파일 | 활용 메서드 |
|------|-----------|
| `QdrantVectorStore` | `AsyncQdrantClient.delete()` + `count()` 직접 사용 |
| `ElasticsearchRepository` | `delete_by_query()` |
| `DocumentMetadataRepository` | `find_by_document_id()`, `delete_by_document_id()` |
| `CollectionPermissionService` | `find_permission()` |
| `ActivityLogService` | `log(ActionType.DELETE_DOCUMENT)` |

---

## 4. Test Results

### 테스트 현황

| 테스트 파일 | 테스트 수 | 결과 |
|------------|----------|------|
| `tests/domain/doc_browse/test_document_delete_policy.py` | 7 | ✅ 전체 통과 |
| `tests/application/doc_browse/test_delete_document_use_case.py` | 9 | ✅ 전체 통과 |
| 기존 doc_browse 테스트 (get_chunks, list_documents) | 15 | ✅ 회귀 없음 |
| **합계** | **31** | **✅ 전체 통과** |

### 테스트 커버리지 상세

**Policy 테스트 (7개)**
- 업로더 본인 삭제 허용
- 컬렉션 소유자 삭제 허용
- ADMIN 삭제 허용
- 관계 없는 사용자 거부
- `collection_owner_id=None` + 업로더 → 허용
- `collection_owner_id=None` + 비업로더 → 거부
- `user_id` str↔int 타입 변환

**UseCase 테스트 (9개)**
- 단건 삭제 성공 (업로더)
- 문서 미존재 → DocumentNotFoundError
- 권한 없음 → PermissionDeniedError
- ES 삭제 실패 시 계속 진행
- 컬렉션 소유자 삭제 성공
- ADMIN 역할 삭제 성공
- 일괄 삭제 전체 성공
- 일괄 삭제 부분 실패 (Qdrant 장애)
- 일괄 삭제 권한 사전 검증 실패 → 전체 403

---

## 5. Gap Analysis Results

### 초기 분석: 95%

| 카테고리 | 점수 |
|---------|------|
| Design Match | 93% |
| Architecture Compliance | 100% |
| Convention Compliance | 98% |
| Test Coverage | 90% |

### 발견된 Gap 및 수정 내역

| # | Gap | 심각도 | 수정 내용 |
|---|-----|--------|----------|
| 1 | `user_role` 하드코딩 (`"user"`) | Medium | `execute_single`/`execute_batch`에 `user_role` 파라미터 추가, Router에서 `X-User-Role` 헤더로 전달 |
| 2 | Batch 부분 실패 테스트 누락 | Medium | `test_batch_partial_failure` 추가 (Qdrant 장애 시나리오) |
| 3 | ADMIN 역할 테스트 누락 | Low | `test_admin_can_delete_any_document` 추가 |

### 수정 후: ~98%

남은 경미한 차이:
- `DocumentDeletePolicy`에 `@dataclass` 데코레이터 없음 (상태 없는 클래스라 불필요)
- 통합 테스트(TestClient) 미작성 (프론트엔드 연동 시 추가 예정)
- DI에서 per-request 생성 방식 (DB-001 세션 규칙상 오히려 개선)

---

## 6. Architecture Compliance

| 규칙 | 준수 |
|------|------|
| Domain → Infrastructure 참조 금지 | ✅ `policies.py`는 순수 판단 로직만 |
| Router에 비즈니스 로직 금지 | ✅ 에러 변환(HTTPException)만 수행 |
| print() 사용 금지 (logger 필수) | ✅ StructuredLogger 사용 |
| 함수 길이 40줄 이하 | ✅ |
| if 중첩 2단계 이하 | ✅ |
| 명시적 타입 사용 | ✅ TYPE_CHECKING + typing 활용 |
| Repository 내부 commit/rollback 금지 | ✅ flush만 사용 |

---

## 7. Error Handling Summary

| 에러 상황 | HTTP | 동작 |
|----------|------|------|
| 문서 미존재 | 404 | `DocumentNotFoundError` |
| 권한 없음 | 403 | `PermissionDeniedError` |
| Qdrant 삭제 실패 | 500 | Exception 전파 |
| ES 삭제 실패 | — | warning 로그, 삭제 계속 진행 |
| Activity Log 실패 | — | warning 로그, 삭제 결과 정상 반환 |
| 일괄 삭제 개별 실패 | 200 | `status: "failed"` + `error` 메시지 포함 |

---

## 8. Lessons Learned

1. **기존 인프라 활용도 높음**: `delete_by_metadata`, `delete_by_query`, `delete_by_document_id`가 이미 구현되어 있어 UseCase에서 조합만 하면 됨
2. **DI per-request 패턴**: main.py의 기존 싱글톤 참조 설계보다 per-request 생성이 DB 세션 규칙(DB-001)에 더 적합
3. **ES 실패 허용 설계**: ES는 보조 저장소이므로 실패 시 경고만 남기고 진행하는 패턴이 운영 안정성에 기여
4. **user_role 전달 필요**: 헤더 기반 인증 시스템에서는 역할 정보도 명시적으로 전달해야 Policy가 제대로 동작함
