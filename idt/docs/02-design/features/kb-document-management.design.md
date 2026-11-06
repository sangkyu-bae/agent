# kb-document-management Design Document

> **Summary**: 신규 `DeleteKbDocumentUseCase`가 권한·요약 잡을 검사하고, 기존 `DeleteDocumentUseCase`의 `delete_verified()`로 저장소를 엄격하게 삭제한다. KB 상세 화면에는 행 단위 삭제를 추가하고 컬렉션 삭제 API는 토큰 인증으로 바꾼다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master, PR #83 머지 후)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft
> **Planning Doc**: [kb-document-management.plan.md](../../01-plan/features/kb-document-management.plan.md)

### Pipeline References

| 단계 | 문서 | 상태 |
|------|------|------|
| Phase 1~4 | 해당 없음 | N/A |

---

## Context Anchor

> Plan 문서에서 복사했다. Design → Do 전환에서 전략 맥락을 유지한다.

| Key | Value |
|-----|-------|
| **WHY** | S1의 "업로드 → 저장 상태 확인" 뒤에 되돌리기 단계가 없어 P2가 컬렉션 화면이나 DB로 우회해야 한다. |
| **WHO** | P2(KB 운영자·에이전트 소유자). 삭제 주체는 KB 소유자, ADMIN, 문서 업로더. |
| **RISK** | 삭제는 되돌릴 수 없다. 권한 판정 오류, 저장소 부분 실패로 인한 고아 청크, 요약 잡과의 경합이 주요 위험이다. |
| **SUCCESS** | 실제 Qdrant·ES·MySQL에서 삭제 후 해당 `document_id`의 데이터 0건, 권한 없는 사용자 403, 저장소 실패 시 메타데이터 유지 후 재시도 성공, 미인증 컬렉션 삭제 거부. |
| **SCOPE** | KB 문서 단건 삭제(백엔드+프론트) + 컬렉션 문서 삭제 DELETE 2개 인증 전환. KB 삭제 벡터 정리·일괄 삭제·조회 API 인증은 제외. |

---

## 1. Overview

### 1.1 Design Goals

1. 권한 판정을 KB 정책 한 곳에 모아 API 검사와 버튼 노출이 같은 규칙을 쓰게 한다.
2. 저장소 삭제가 끝나기 전에는 재시도 진입점인 메타데이터를 잃지 않는다.
3. 컬렉션 경로의 기존 메서드와 테스트를 바꾸지 않는다.
4. 요약 잡 러너를 수정하지 않는다.

### 1.2 Design Principles

- 권한은 domain, 흐름은 application, 예외 매핑은 라우터가 맡는다.
- 공유 메서드에 플래그를 넣지 않고 진입점을 분리한다.
- 메타데이터·잡 행·활동 로그는 요청 세션 하나로 묶어 함께 커밋한다.
- API 변경은 additive로 한다. 예외는 의도된 인증 전환(FR-09) 1건이다.

### 1.3 Plan 대비 정정

| Plan 기술 | 코드 실측 | Design 처리 |
|-----------|-----------|-------------|
| §6.1 `SectionSummaryJobStoreInterface`와 구현체에 삭제 추가 | 싱글턴 스토어는 호출마다 별도 세션으로 즉시 커밋한다(`job_repository.py:131-146`). 스토어로 지우면 메타데이터와 트랜잭션이 갈린다. | 요청 세션의 `SectionSummaryJobRepository`에만 `delete_by_document()`를 추가한다. 스토어·ABC는 변경하지 않는다. |
| §7.2 삭제 순서 Qdrant → ES → 잡 행 → 메타 | 메타와 잡 행은 같은 트랜잭션이라 둘의 순서는 결과에 영향이 없다. | Qdrant → ES → (메타 + 활동 로그 + 잡 행 1트랜잭션). |
| §6.1 변경 자원 목록 | `KbDocumentSummary`에 업로더 정보가 없어 `can_delete`를 계산할 수 없다(`doc_browse/schemas.py:48-55`). | `KbDocumentSummary.user_id`를 추가하고 `document_metadata_repository.py:230`을 수정한다. `user_id` 컬럼은 이미 있어 스키마 변경은 없다. |
| SC-5 미인증 401 | `HTTPBearer()` 기본값의 무토큰 응답 코드는 FastAPI 버전에 따라 다르다. 위키는 이 프로젝트의 실측을 401로 기록했다. | 라우터 테스트 Red 단계에서 실제 코드를 먼저 확인한다. 401이 아니면 사용자에게 보고한다. |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | A: 최소 변경 | B: 클린 | C: 실용 절충 |
|------|-------------|---------|-------------|
| **방식** | `execute_single`에 플래그 추가 | 저장소 삭제 포트·어댑터 추출 | 신규 UseCase + `delete_verified()` |
| **신규 파일(테스트 제외)** | 1 | 4~5 | 2 |
| **수정 파일(테스트 제외)** | 약 13 | 약 16 | 약 14 |
| **복잡도** | 낮음 | 높음 | 중간 |
| **유지보수성** | 낮음 | 높음 | 높음 |
| **작업량** | 낮음 | 높음 | 중간 |
| **위험** | 플래그 오용 시 권한 생략 | 컬렉션 경로 회귀 | 낮음 |

**선택**: Option C — **근거**: KB 정책과 잡 검사를 컬렉션 UseCase 밖에 두면서 기존 메서드를 바꾸지 않는다. 사용자 선택.

### 2.1 Component Diagram

```
KnowledgeBaseDetailPage
  └─ KbDocumentTable ─ IconButton(can_delete=true 행)
  └─ DeleteKbDocumentDialog ─ useDeleteKbDocument ─ knowledgeBaseService
                                                        │ DELETE (Bearer)
knowledge_base_router.delete_kb_document ◀──────────────┘
  └─ DeleteKbDocumentUseCase
       ├─ KbDocumentGuard ── KnowledgeBaseUseCase, DocumentMetadataRepository
       ├─ KnowledgeBasePolicy.can_delete_document
       ├─ SectionSummaryJobRepository + SectionSummaryJobPolicy.is_stale
       └─ DeleteDocumentUseCase.delete_verified
            ├─ Qdrant 필터 삭제
            ├─ ES delete_by_query
            ├─ DocumentMetadataRepository.delete_by_document_id
            └─ ActivityLogService
```

### 2.2 Data Flow

```
요청 → 인증 → guard.ensure(KB 404 / 읽기 403 / 문서 404)
     → can_delete_document(403)
     → 요약 잡 검사(409)
     → Qdrant 삭제 → ES 삭제 ──실패──▶ 503, DB 변경 없음
     → 메타 삭제 + 활동 로그 + 잡 행 삭제
     → 요청 종료 시 1회 커밋
```

### 2.3 Dependencies

| 구성요소 | 의존 대상 | 목적 |
|----------|-----------|------|
| `DeleteKbDocumentUseCase` | `KbDocumentGuard` | 존재·읽기 권한·소속 검증 재사용 |
| `DeleteKbDocumentUseCase` | `KnowledgeBasePolicy` | 삭제 권한 판정 |
| `DeleteKbDocumentUseCase` | `SectionSummaryJobRepository` | 진행 중 잡 조회, 행 삭제. 애플리케이션의 저장소 직접 참조는 `SectionSummaryQueryUseCase` 선례를 따른다 |
| `DeleteKbDocumentUseCase` | `SectionSummaryJobPolicy` | stale 판정 재사용 |
| `DeleteKbDocumentUseCase` | `DeleteDocumentUseCase` | 저장소 삭제 재사용 |

---

## 3. Data Model

DB 스키마 변경은 없다. 마이그레이션은 0건이다. 값 객체만 additive로 바꾼다.

```python
# domain/doc_browse/schemas.py
class KbDocumentSummary:
    ...
    user_id: str = ""            # 추가: document_metadata.user_id

# application/knowledge_base/content_browse_guard.py
class KbDocumentContext:
    ...
    kb: KnowledgeBase | None = None   # 추가: 정책 판정용(재조회 방지)
    uploader_id: str = ""             # 추가: document_metadata.user_id

# application/knowledge_base/list_documents_use_case.py
class KbDocumentItem:
    ...
    can_delete: bool = False     # 추가
```

삭제 대상 데이터는 다음과 같다.

| 저장소 | 대상 | 조건 |
|--------|------|------|
| Qdrant | child·parent 청크, 섹션 요약, 문서 요약 | 문서 메타데이터의 `collection_name`(문서가 실제로 저장된 컬렉션) 내 `document_id` 일치 |
| ES | 위와 동일 | `settings.es_index` 내 `document_id` 일치(keyword) |
| MySQL | `document_metadata` 1행 | `document_id` |
| MySQL | `section_summary_job` 0~1행 | `document_id` |

`search_history`, 실행 관측의 `document_id`는 이력이므로 유지한다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 설명 | 인증 | 변경 |
|--------|------|------|------|------|
| DELETE | `/api/v1/knowledge-bases/{kb_id}/documents/{document_id}` | KB 문서 단건 삭제 | Bearer | 신규 |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents` | 문서 목록 | Bearer | `can_delete` 추가 |
| DELETE | `/api/v1/collections/{collection_name}/documents/{document_id}` | 컬렉션 문서 삭제 | 헤더 → Bearer | 인증 전환 |
| DELETE | `/api/v1/collections/{collection_name}/documents` | 컬렉션 문서 일괄 삭제 | 헤더 → Bearer | 인증 전환 |

### 4.2 Detailed Specification

#### `DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}`

**Response (200):**

```json
{
  "kb_id": "kb-1",
  "document_id": "doc-1",
  "filename": "규정.pdf",
  "deleted_qdrant_chunks": 42,
  "deleted_es_chunks": 42,
  "status": "deleted"
}
```

스키마 이름은 `KbDocumentDeleteResponse`다.

**오류 응답 (판정 순서대로):**

| 순서 | 코드 | 상황 |
|------|------|------|
| 1 | 인증 실패 코드 | 토큰 없음·만료 |
| 2 | 404 | KB 없음 |
| 3 | 403 | KB 읽기 권한 없음 |
| 4 | 404 | 문서 없음, 다른 KB 소속, `kb_id` NULL |
| 5 | 403 | 삭제 권한 없음 |
| 6 | 409 | 요약 잡 진행 중 |
| 7 | 503 | Qdrant 또는 ES 삭제 실패 |

#### `GET /api/v1/knowledge-bases/{kb_id}/documents`

`documents[]` 항목에 `can_delete: boolean`을 추가한다. 나머지 필드는 그대로다.

#### 컬렉션 DELETE 2개

- `X-User-Id`, `X-User-Role` 파라미터를 제거하고 `current_user: User = Depends(get_current_user)`를 쓴다.
- UseCase에는 `user_id=str(current_user.id)`, `user_role=current_user.role.value`를 넘긴다.
- 요청·응답 본문과 404·403 동작은 그대로다.

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
문서 3                                          [+ 문서 업로드]
┌──────────────────────────────────────────────────────────┐
│ 파일명     청크 수  청킹 방식  업로드일   검색         관리 │
│ 규정.pdf   42      기본       11-02     [이 문서에서]  🗑 │
│ 약관.pdf   10      기본       11-01     [이 문서에서]     │ ← can_delete=false
└──────────────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
휴지통 클릭 → 확인 다이얼로그 → 삭제
  ├─ 성공: 다이얼로그 닫기 + 목록 갱신 + 드릴다운·검색 범위 해제
  └─ 실패: 다이얼로그 유지 + 서버 메시지 표시 + 다시 시도 가능
```

### 5.3 Component List

| 구성요소 | 위치 | 책임 |
|----------|------|------|
| `KbDocumentTable` | `components/knowledge-base/` | 선택 prop `onDeleteDocument`, "관리" 열, `IconButton` |
| `DeleteKbDocumentDialog` | `components/knowledge-base/` (신규) | `DeleteKnowledgeBaseDialog`와 같은 형태의 `ConfirmDialog` 래퍼 |
| `KnowledgeBaseDetailPage` | `pages/` | 삭제 대상·오류 상태, 성공 후 상태 해제 |
| `useDeleteKbDocument` | `hooks/useKnowledgeBases.ts` | 뮤테이션과 캐시 무효화 |

훅의 무효화는 `onSettled`에서 `queryKeys.knowledgeBases.all`로 실행한다. 실패한 경우에도 이미 삭제된 문서나 일부 지워진 청크 수가 목록에 반영된다. 페이지는 `mutate`의 `onSuccess`에서 대상 문서의 `selectedDoc`, `searchScopeDoc`을 해제한다.

오류 표시는 `authApiClient`가 만든 `ApiError`를 쓴다(`err.response` 금지). 409·503은 서버가 보낸 한국어 메시지를 그대로 쓰고, 403·404는 서버 메시지가 영문이라 화면 문구로 바꾼다.

### 5.4 Page UI Checklist

#### KnowledgeBaseDetailPage

- [ ] 표: `onDeleteDocument`가 전달되면 "관리" 열 표시
- [ ] 행: `can_delete=true`일 때만 휴지통 `IconButton` 표시
- [ ] 버튼: `aria-label`이 `{파일명} 삭제`, `tone="danger"`, `Trash2` 아이콘
- [ ] 버튼: 클릭해도 행 드릴다운이 열리지 않음
- [ ] 다이얼로그: 제목 "문서 삭제", 파일명 강조
- [ ] 다이얼로그: "삭제하면 복구할 수 없으며 이 문서의 청크와 요약이 검색에서 제외됩니다." 안내
- [ ] 다이얼로그: 확인 버튼 "삭제", 대기 중 비활성·스피너
- [ ] 다이얼로그: 대기 중에는 닫기 동작 무시
- [ ] 다이얼로그: 실패 메시지 표시, 다시 열면 이전 오류 없음
- [ ] 성공: 문서 수 감소, 선택된 드릴다운 패널 닫힘, 검색 범위 칩 해제

---

## 6. Error Handling

### 6.1 Error Code Definition

| 코드 | 메시지 | 원인 | 처리 |
|------|--------|------|------|
| 403 | 이 문서를 삭제할 권한이 없습니다 (화면 문구) | 권한 없음 | 다이얼로그에 표시. 서버 메시지는 영문이라 화면에서 바꾼다 |
| 404 | 이미 삭제되었거나 찾을 수 없는 문서입니다 (화면 문구) | 문서·KB 없음 | 표시 후 목록 재조회 |
| 409 | 섹션 요약이 진행 중인 문서는 삭제할 수 없습니다. 요약이 끝난 뒤 다시 시도해 주세요. | 활성 잡 | 표시, 재시도 가능 |
| 503 | 저장소에서 문서를 삭제하지 못했습니다. 문서는 유지되었으니 다시 시도해 주세요. | Qdrant·ES 오류 | 표시, 재시도 가능 |

### 6.2 Exception Mapping

```python
# application/doc_browse/delete_document_use_case.py
class StoreDeleteFailedError(Exception): ...      # DeleteDocumentUseCase 내부 클래스

# application/knowledge_base/delete_document_use_case.py
class DocumentBusyError(Exception): ...           # DeleteKbDocumentUseCase 내부 클래스
```

기존 `DocumentNotFoundError`, `PermissionDeniedError`의 내부 클래스 관례를 따른다. 라우터는 두 예외를 각각 409, 503으로 바꾸고 `PermissionError`, `ValueError`는 기존 `_raise_http`로 처리한다. `HTTPException`이 `get_session` 밖으로 전파되므로 트랜잭션은 롤백된다. 이 시점에 DB 변경은 없다.

저장소 실패는 `logger.error(..., exception=e, request_id=...)`로 스택 트레이스를 남긴다.

### 6.3 재시도와 알려진 한계

- Qdrant만 삭제되고 ES가 실패해도 재시도는 안전하다. 없는 포인트를 지우면 0건이 된다.
- 재시도 시 응답의 `deleted_*_chunks`는 그 요청에서 지운 수만 뜻한다.
- 물리 컬렉션이나 ES 인덱스 자체가 없으면 503이 반복될 수 있다. 정상 운영에서는 발생하지 않는 상태이므로 이번 범위에서 처리하지 않는다.

---

## 7. Security Considerations

- [ ] 삭제 경로 3개 모두 `get_current_user` 인증을 거친다.
- [ ] 위조한 `X-User-Id`, `X-User-Role` 헤더가 판정에 쓰이지 않는다.
- [ ] 읽기 권한과 삭제 권한을 별도로 검사한다.
- [ ] 다른 KB 문서는 존재 여부를 드러내지 않고 404로 응답한다.
- [ ] `delete_verified()`는 권한을 검사하지 않으므로 docstring에 호출자 책임을 명시하고, 호출 지점을 AST 테스트로 `DeleteKbDocumentUseCase` 하나로 제한한다.
- [ ] 활동 로그에 `kb_id`, `document_id`, `filename`, 삭제 수, 사용자를 남긴다.
- 잔존 위험: `doc_browse_router` GET 2개는 인증이 없다. 이번 범위 밖이며 Report에서 후속으로 이월한다.

---

## 8. Test Plan

### 8.1 Test Scope

| 유형 | 대상 | 도구 | 단계 |
|------|------|------|------|
| 단위 | 정책, UseCase, 저장소 | pytest, 실 DB 세션(저장소) | Do |
| L1 API | 라우터 실요청 | FastAPI TestClient | Do |
| 단위 | 훅, 표, 다이얼로그, 페이지 | Vitest, RTL, MSW | Do |
| L3 실런 | 전체 흐름 | 실 MySQL·Qdrant·ES + 브라우저 | Do 종료 전 |

### 8.2 L1: API Test Scenarios

| # | 엔드포인트 | 시나리오 | 기대 |
|---|-----------|----------|------|
| 1 | KB DELETE | KB 소유자 | 200, 응답 필드 전체 |
| 2 | KB DELETE | ADMIN | 200 |
| 3 | KB DELETE | 업로더 본인(소유자 아님, 부서 KB) | 200 |
| 4 | KB DELETE | 같은 부서 다른 멤버 | 403 |
| 5 | KB DELETE | PUBLIC KB 일반 열람자 | 403 |
| 6 | KB DELETE | 다른 KB 문서 ID | 404 |
| 7 | KB DELETE | 없는 KB, 없는 문서 | 404 |
| 8 | KB DELETE | `processing` 비-stale 잡 | 409 |
| 9 | KB DELETE | stale 잡, `completed`, `failed`, 잡 없음 | 200 |
| 10 | KB DELETE | 저장소 실패 | 503 |
| 11 | KB DELETE | 토큰 없음 | 인증 실패 |
| 12 | KB 목록 | 업로더·비업로더 혼합 | 항목별 `can_delete` |
| 13 | 컬렉션 DELETE 2개 | 토큰 없이 `X-User-Role: admin` | 인증 실패, UseCase 미호출 |
| 14 | 컬렉션 DELETE 2개 | 일반 사용자 토큰 + 위조 admin 헤더 | `user_role="user"`로 호출 |
| 15 | 컬렉션 DELETE 2개 | ADMIN 토큰 | `user_role="admin"`으로 호출 |

단위 테스트는 다음을 단언한다.

- `can_delete_document`: ADMIN, 소유자, 업로더, 타인, 빈 `uploader_id`, `user.id=None`.
- `DeleteKbDocumentUseCase`: 판정 순서, 실패 시 `delete_verified`와 잡 삭제 미호출, 성공 시 호출 인자.
- `delete_verified`: Qdrant 실패·ES 실패 시 `StoreDeleteFailedError`, 메타 삭제·로그 미호출, 로그 실패는 무시, `kb_id`가 활동 로그에 포함.
- 기존 `test_delete_document_use_case.py`는 수정 없이 통과.
- `delete_by_document`: 대상 행만 삭제, 없는 문서는 0건.
- 호출 지점 AST 계약: `delete_verified` 호출은 `DeleteKbDocumentUseCase`에만 존재.
- DI 배선: `create_app()`의 `dependency_overrides`에 신규 플레이스홀더 존재.

### 8.3 L2: UI Action Test Scenarios

| # | 대상 | 동작 | 기대 |
|---|------|------|------|
| 1 | 표 | `can_delete` 혼합 렌더 | 해당 행에만 버튼 |
| 2 | 표 | 삭제 클릭 | `onDeleteDocument` 호출, `onRowClick` 미호출 |
| 3 | 표 | prop 미전달 | "관리" 열 없음(기존 사용 불변) |
| 4 | 훅 | 성공·실패 | 엔드포인트 호출, 양쪽 모두 무효화 |
| 5 | 페이지 | 삭제 성공(MSW) | 목록 감소, 드릴다운·검색 범위 해제 |
| 6 | 페이지 | 409·503(MSW) | 서버 메시지 표시, 다이얼로그 유지 |
| 7 | 페이지 | 대기 중 확인 재클릭 | 요청 1회 |

이중 제출 테스트는 비활성 버튼 클릭이 아니라 `isPending` 전달과 요청 횟수를 단언한다.

### 8.4 L3: E2E Scenario Test Scenarios

| # | 시나리오 | 단계 | 성공 기준 |
|---|----------|------|-----------|
| 1 | S1 되돌리기 | 업로드 → 드릴다운 확인 → 삭제 | SC-1, SC-6. Qdrant·ES·MySQL 직접 조회로 0건 확인 |
| 2 | 다른 문서 보존 | 같은 컬렉션 다른 KB에 문서 업로드 후 삭제 | 다른 KB 문서 유지 |
| 3 | 검색 제외 | 삭제 전후 리트리버 테스트 | SC-7 |
| 4 | 부분 실패 복구 | ES 중단 → 삭제 503 → ES 복구 → 재시도 | SC-3 |
| 5 | 요약 잡 | 요약 프로파일 KB 업로드 직후 삭제 → 완료 후 삭제 | SC-4 |
| 6 | 컬렉션 화면 | `CollectionDocumentsPage`에서 삭제 | SC-5 회귀 없음 |

실저장소를 띄울 수 없으면 해당 항목을 완료로 표기하지 않고 `e2e-carryover-checklist` 이월 대상으로 남긴다.

### 8.5 Seed Data Requirements

| 대상 | 최소 수량 | 조건 |
|------|-----------|------|
| 사용자 | 3 | 소유자, 같은 부서 멤버, ADMIN |
| KB | 2 | 같은 물리 컬렉션 사용 |
| 문서 | 3 | 업로더가 다른 문서 포함. 시나리오 5는 요약 프로파일 활성 KB |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| 레이어 | 책임 | 위치 |
|--------|------|------|
| Interfaces | 인증, 예외 매핑, 응답 스키마 | `src/api/routes/` |
| Application | 삭제 흐름 조립 | `src/application/knowledge_base/`, `src/application/doc_browse/` |
| Domain | 삭제 권한 규칙, stale 규칙 | `src/domain/knowledge_base/policy.py`, `src/domain/section_summary/policy.py` |
| Infrastructure | 저장소 삭제 쿼리 | `src/infrastructure/section_summary/job_repository.py` |

### 9.2 Dependency Rules

domain은 외부를 참조하지 않는다. 라우터에 권한 판단을 두지 않는다. 저장소는 commit·rollback을 호출하지 않는다.

### 9.3 File Import Rules

`KbDocumentContext`의 `kb` 추가로 application 내부 참조만 늘어난다. domain에 신규 import는 없다.

### 9.4 This Feature's Layer Assignment

| 구성요소 | 레이어 | 위치 |
|----------|--------|------|
| `can_delete_document` | Domain | `domain/knowledge_base/policy.py` |
| `DeleteKbDocumentUseCase` | Application | `application/knowledge_base/delete_document_use_case.py` |
| `delete_verified` | Application | `application/doc_browse/delete_document_use_case.py` |
| `delete_by_document` | Infrastructure | `infrastructure/section_summary/job_repository.py` |
| `delete_kb_document` | Interfaces | `api/routes/knowledge_base_router.py` |

### 9.5 핵심 구현 스케치

```python
# domain/knowledge_base/policy.py
@staticmethod
def can_delete_document(user: User, kb: KnowledgeBase, uploader_id: str) -> bool:
    if KnowledgeBasePolicy.can_delete(user, kb):
        return True
    return bool(uploader_id) and user.id is not None and uploader_id == str(user.id)

# application/knowledge_base/delete_document_use_case.py
class DeleteKbDocumentUseCase:
    class DocumentBusyError(Exception):
        pass

    async def execute(self, kb_id, document_id, user, request_id):
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)
        if not self._policy.can_delete_document(user, ctx.kb, ctx.uploader_id):
            raise PermissionError(...)
        await self._ensure_not_busy(document_id, request_id)
        result = await self._deleter.delete_verified(
            ctx.collection_name, document_id, ctx.filename,
            str(user.id), request_id, extra_detail={"kb_id": kb_id},
        )
        await self._job_repo.delete_by_document(document_id, request_id)
        return result

    async def _ensure_not_busy(self, document_id, request_id):
        job = await self._job_repo.find_by_document(document_id, request_id)
        if job is None or job.status not in ACTIVE_JOB_STATUSES:
            return
        if self._job_policy.is_stale(job, datetime.now(), self._stale_seconds):
            return
        raise self.DocumentBusyError(BUSY_MESSAGE)
```

`datetime.now()`와 `settings.section_summary_stale_seconds`는 재시도 판정(`query_use_case.py:63-65`)과 같은 기준을 쓴다.

```python
# application/doc_browse/delete_document_use_case.py
class StoreDeleteFailedError(Exception):
    pass

async def delete_verified(
    self, collection_name, document_id, filename,
    user_id, request_id, extra_detail=None,
) -> DeleteDocumentResult:
    """호출자가 권한을 검증한 뒤 문서를 삭제한다. 저장소 실패 시 메타데이터를 유지한다."""
    deleted_qdrant, deleted_es = await self._purge_stores_strict(
        collection_name, document_id, request_id
    )
    await self._metadata_repo.delete_by_document_id(document_id, request_id)
    await self._log_activity(..., extra_detail=extra_detail)
    return DeleteDocumentResult(...)
```

`_log_activity`에 선택 인자 `extra_detail`을 추가한다. 기존 호출은 그대로 동작한다.

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예시 |
|------|------|------|
| 백엔드 UseCase | PascalCase + `UseCase` | `DeleteKbDocumentUseCase` |
| 응답 스키마 | `...Response` | `KbDocumentDeleteResponse` |
| 프론트 컴포넌트 | PascalCase | `DeleteKbDocumentDialog` |
| 훅 | `use` + 동사 | `useDeleteKbDocument` |
| 엔드포인트 상수 | UPPER_SNAKE | `KNOWLEDGE_BASE_DOCUMENT_DETAIL` |

### 10.2 Import Order

기존 파일 순서를 따른다. 프론트는 절대 경로 `@/`를 쓴다.

### 10.3 Environment Variables

추가 없음. 기존 `settings.section_summary_stale_seconds`, `settings.es_index`를 쓴다.

### 10.4 This Feature's Conventions

| 항목 | 적용 |
|------|------|
| DB 세션 | 요청 세션 1개를 가드, 메타 저장소, 잡 저장소, 활동 로그가 공유 |
| 클라이언트 | Qdrant·ES는 팩토리 생성 시 1회만 만들어 재사용 |
| 함수 크기 | 40줄 이내, if 2단 이내 |
| 프론트 스타일 | 신규 코드는 디자인 토큰과 `IconButton` 사용. `KbDocumentTable`의 기존 클래스는 재작성하지 않음 |
| 프론트 타입 | `can_delete`는 필수 필드. MSW와 테스트 픽스처를 함께 수정 |
| 설계 추적 | 주요 파일에 `Design Ref`, `Plan SC` 주석 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/doc_browse/schemas.py                         수정
├── domain/knowledge_base/policy.py                      수정
├── application/doc_browse/delete_document_use_case.py   수정
├── application/knowledge_base/content_browse_guard.py   수정
├── application/knowledge_base/delete_document_use_case.py  신규
├── application/knowledge_base/list_documents_use_case.py   수정
├── infrastructure/doc_browse/document_metadata_repository.py  수정
├── infrastructure/section_summary/job_repository.py     수정
├── api/routes/knowledge_base_router.py                  수정
├── api/routes/doc_browse_router.py                      수정
└── api/main.py                                          수정

idt_front/src/
├── constants/api.ts                                     수정
├── types/knowledgeBase.ts                               수정
├── services/knowledgeBaseService.ts                     수정
├── hooks/useKnowledgeBases.ts                           수정
├── components/knowledge-base/KbDocumentTable.tsx        수정
├── components/knowledge-base/DeleteKbDocumentDialog.tsx 신규
├── pages/KnowledgeBaseDetailPage/index.tsx              수정
└── __tests__/mocks/handlers.ts                          수정
```

### 11.2 Implementation Order

1. [ ] 정책 `can_delete_document` (Red → Green)
2. [ ] `KbDocumentSummary`, 저장소 매핑, `KbDocumentContext` 확장
3. [ ] `delete_by_document`
4. [ ] `delete_verified`, `StoreDeleteFailedError`
5. [ ] `DeleteKbDocumentUseCase`
6. [ ] 목록 `can_delete`
7. [ ] KB DELETE 라우트, 플레이스홀더, `main.py` 팩토리
8. [ ] 컬렉션 DELETE 인증 전환
9. [ ] 프론트 계약 동기화와 훅
10. [ ] 표, 다이얼로그, 페이지
11. [ ] 실런 검증

DI는 `create_kb_document_delete_factory(kb_use_case_factory)`를 추가한다. Qdrant·ES 클라이언트는 함수 스코프에서 1회 만들고, 내부 팩토리가 `session`으로 가드, 메타 저장소, 잡 저장소, 활동 로그, `DeleteDocumentUseCase`를 조립한다. 기존 `_delete_document_uc_factory`는 재사용하지 않는다. 요청마다 클라이언트를 만들기 때문이다.

### 11.3 Session Guide

#### Module Map

| 모듈 | Scope Key | 설명 | 예상 턴 |
|------|-----------|------|---------|
| 백엔드 코어 | `module-1` | 구현 순서 1~6. 정책, 값 객체, 저장소, UseCase | 25-30 |
| API·인증 | `module-2` | 구현 순서 7~8. 라우터, DI, 인증 전환, L1 | 20-25 |
| 프론트 | `module-3` | 구현 순서 9~10. 계약 동기화, UI, L2 | 25-30 |
| 실런 검증 | `module-4` | 구현 순서 11. L3 시나리오 6종 | 15-20 |

#### Recommended Session Plan

| 세션 | 단계 | 범위 | 턴 |
|------|------|------|-----|
| 1 | Plan + Design | 전체 | 완료 |
| 2 | Do | `--scope module-1,module-2` | 45-55 |
| 3 | Do | `--scope module-3` | 25-30 |
| 4 | Do + Check | `--scope module-4` 후 분석 | 30-40 |

회귀 기준은 master 대비 정렬된 `FAILED` 목록 diff다. 백엔드 테스트는 `uv run python -m pytest`로 실행한다. 프론트는 `tsc -b`까지 확인한다.

---

## FR 역추적

| FR | 설계 위치 | 테스트 |
|----|-----------|--------|
| FR-01 | §4.2, §9.5 | L1 #1 |
| FR-02 | §9.5 정책 | 단위, L1 #1~5 |
| FR-03 | §2.2, §4.2 | 단위 순서, L1 #4~8 |
| FR-04 | §6.2, §9.5 | 단위, L1 #10, L3 #4 |
| FR-05 | §9.5 `_ensure_not_busy` | L1 #8~9, L3 #5 |
| FR-06 | §1.3, §9.5 | 단위, L3 #1 |
| FR-07 | §9.5 `extra_detail` | 단위 |
| FR-08 | §3, §4.2 | L1 #12 |
| FR-09 | §4.2 | L1 #13~15, L3 #6 |
| FR-10 | §5.3, §5.4 | L2 #1~3 |
| FR-11 | §5.3, §5.4, §6.1 | L2 #6~7 |
| FR-12 | §5.3 | L2 #4~5 |
| FR-13 | §11.1 | `tsc -b`, L2 #4 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | 초안 작성. Option C 선택, Plan 정정 4건 반영 | 배상규 + Claude |
| 0.2 | 2026-11-03 | Check 반영: §3 Qdrant 삭제 위치를 문서 메타데이터의 컬렉션으로, §6.1 403·404를 화면 문구로 수정 | 배상규 + Claude |
