# kb-document-management Planning Document

> **Summary**: KB 운영자가 KB 상세 화면에서 잘못 올린 문서를 직접 삭제하고, 벡터·키워드 저장소에 남는 데이터 없이 정리되도록 한다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master, PR #83 머지 후)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft
> **원천**: `docs/proposals/2026-10-15.md` 후보 #4 (§2-4). 제안서의 전제 2건을 실측으로 정정했다(§1.2).

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | KB 상세 화면에는 문서 삭제가 없다. 잘못 올린 문서를 지우려면 컬렉션 화면이나 DB로 가야 해서 S1 성공 기준 "DB/Swagger 직접 조작 0회"를 어긴다. 우회 경로인 컬렉션 삭제 API에는 인증도 없다. |
| **해결** | `DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}`와 문서 행 삭제 버튼을 추가한다. 삭제 권한은 KB 소유자·ADMIN·문서 업로더로 제한하고, 요약 잡 진행 중에는 409로 막으며, 저장소 삭제가 모두 성공해야 메타데이터를 지운다. 컬렉션 삭제 API 2개는 토큰 인증으로 바꾼다. |
| **기능·UX 효과** | 권한이 있는 문서 행에만 삭제 버튼이 보인다. 확인 다이얼로그를 거쳐 삭제하면 목록·드릴다운·검색 범위가 함께 정리된다. 실패한 문서는 목록에 남아 다시 시도할 수 있다. |
| **핵심 가치** | P2가 개발자 도움 없이 업로드를 되돌릴 수 있어 S1 폐루프의 빠진 단계가 메워진다. 삭제한 문서가 검색 근거로 다시 나타나지 않는다. |

---

## Context Anchor

> Design·Do 문서로 전파해 세션 간 맥락을 유지한다.

| Key | Value |
|-----|-------|
| **WHY** | S1의 "업로드 → 저장 상태 확인" 뒤에 되돌리기 단계가 없어 P2가 컬렉션 화면이나 DB로 우회해야 한다. |
| **WHO** | P2(KB 운영자·에이전트 소유자). 삭제 주체는 KB 소유자, ADMIN, 문서 업로더. |
| **RISK** | 삭제는 되돌릴 수 없다. 권한 판정 오류, 저장소 부분 실패로 인한 고아 청크, 요약 잡과의 경합이 주요 위험이다. |
| **SUCCESS** | 실제 Qdrant·ES·MySQL에서 삭제 후 해당 `document_id`의 데이터 0건, 권한 없는 사용자 403, 저장소 실패 시 메타데이터 유지 후 재시도 성공, 미인증 컬렉션 삭제 401. |
| **SCOPE** | KB 문서 단건 삭제(백엔드+프론트) + 컬렉션 문서 삭제 DELETE 2개 인증 전환. KB 삭제 벡터 정리·일괄 삭제·조회 API 인증은 제외. |

---

## 1. Overview

### 1.1 Purpose

KB 운영자가 KB 상세 화면을 벗어나지 않고 문서 업로드를 되돌리게 한다. 삭제 후에는 문서 메타데이터, Qdrant 청크, ES 청크, 섹션·문서 요약, 요약 잡 행이 남지 않아야 한다.

### 1.2 Background

`kb-management-ui`가 범위를 CRUD와 업로드로 줄이면서 문서 삭제를 후속으로 남겼고, 이후 KB 시리즈는 검색과 콘텐츠 브라우저 쪽으로 진행되었다.

제안서는 "`KbDocumentGuard`로 소속을 검증하고 `DeleteDocumentUseCase`에 위임"을 제안했다. 코드 대조 결과 아래 2건은 그대로 쓸 수 없다.

| 제안서 전제 | 실측 | 이 계획의 처리 |
|------------|------|---------------|
| `KbDocumentGuard`로 검증하면 된다 | 가드는 `KnowledgeBaseUseCase.get()`으로 **읽기** 권한만 검사한다(`content_browse_guard.py:47`). PUBLIC KB의 일반 열람자도 통과한다. | 가드 뒤에 삭제 권한 판정을 별도로 둔다(FR-02). |
| `DeleteDocumentUseCase`에 그대로 위임한다 | 내부 `DocumentDeletePolicy`는 ADMIN·업로더·**컬렉션** 소유자를 기준으로 판정한다(`policies.py:12-28`). 공유 컬렉션의 KB 소유자는 거부될 수 있다. ES 실패도 삼킨 뒤 메타데이터를 지운다(`delete_document_use_case.py:260-266`). | KB 경로에서는 권한 판정을 KB 정책으로 대체하고, 저장소 실패를 엄격하게 처리한다(FR-04). |

조사에서 추가로 확인한 사실은 다음과 같다.

- `DocumentMetadata`, `section_summary_job`, Qdrant, ES 외에 `document_id` 컬럼을 가진 테이블은 `search_history`(V015)와 V021의 `ai_run` 계열 1곳이다. 둘 다 이력이므로 삭제 대상이 아니다.
- 섹션·문서 요약은 원문 청크와 같은 컬렉션·인덱스에 같은 `document_id`로 저장되므로(`summary_writer.py`, `document_summary_step.py`) 기존 필터 삭제로 함께 지워진다. Design에서 테스트로 고정한다.
- ES `document_id`는 keyword 매핑이다(`es_index_mappings.py:41`). `match` 쿼리가 다른 문서를 지울 위험은 없다.
- 업로드마다 `document_id`는 새 UUID다(`unified_upload/use_case.py:92`). 재업로드가 `section_summary_job` UQ와 충돌하지 않는다.
- `doc_browse_router`의 DELETE 2개는 `X-User-Id`·`X-User-Role` 헤더를 그대로 신뢰하며, 앱에 인증 미들웨어가 없다(`main.py:5527-5535`). 헤더를 위조하면 인증 없이 임의 문서를 지울 수 있다.

### 1.3 Related Documents

- 제안: `docs/proposals/2026-10-15.md` §2-4
- 시나리오: `docs/USER-SCENARIOS.md` S1
- 선행 설계: `idt/docs/archive/2026-07/kb-management-ui/`, `idt/docs/archive/2026-07/kb-content-browser/`
- 위키: `docs/wiki/backend/db/erd-kb.md`, `docs/wiki/frontend/screens/kb-screens.md`, `docs/wiki/conventions/additive-contract-extension.md`, `docs/wiki/conventions/false-green-quality-gates.md`, `docs/wiki/backend/patterns/app-lifetime-client-singleton.md`, `docs/wiki/frontend/patterns/loading-button-pending-guard.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] KB 문서 단건 삭제 API
- [ ] 문서 삭제 권한 정책(KB 소유자·ADMIN·문서 업로더)
- [ ] 요약 잡 진행 중 삭제 차단, 삭제 시 잡 행 정리
- [ ] KB 경로의 엄격한 저장소 삭제(실패 시 메타데이터 유지)
- [ ] 문서 목록 응답의 삭제 가능 여부 필드(additive)
- [ ] 컬렉션 문서 삭제 DELETE 2개의 토큰 인증 전환
- [ ] KB 상세 화면 삭제 버튼, 확인 다이얼로그, 삭제 후 화면 상태 정리

### 2.2 Out of Scope

| 항목 | 이유 | 후속 |
|------|------|------|
| KB 삭제 시 벡터·ES 정리 | 별도 S 크기 작업. 사용자가 제외 결정 | `kb-vector-cleanup` |
| 문서 일괄 삭제 | 단건으로 S1 되돌리기를 충족한다. 사용자가 제외 결정 | 필요 시 별도 사이클 |
| `doc_browse_router` GET 2개 인증 | 이번 결정 범위는 DELETE 2개다. 목록·청크 조회도 현재 인증이 없다 | 별도 소형 사이클(§5 위험 참고) |
| 문서 소프트 삭제·복구 | 저장소 데이터까지 지우는 것이 목표다 | 없음 |
| 문서 교체(재업로드 시 덮어쓰기), 재청킹 | S1 되돌리기 범위 밖 | 없음 |
| `kb_id` NULL 레거시 문서 | KB 목록에 나타나지 않는다(kb-management-ui D4) | 없음 |
| 삭제 진행 중 요약 재시도 경합의 완전 차단 | §5 참고. 잠금 없이 좁은 시간창을 허용한다 | 없음 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 | 상태 |
|----|----------|----------|------|
| FR-01 | `DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}`를 추가한다. `get_current_user` 인증을 쓰고, 성공 시 `document_id`, `filename`, `deleted_qdrant_chunks`, `deleted_es_chunks`, `status`를 반환한다. | High | Pending |
| FR-02 | 삭제 권한을 `KnowledgeBasePolicy`에 추가한다. ADMIN, KB 소유자, 문서 업로더(`document_metadata.user_id == str(user.id)`)만 허용한다. | High | Pending |
| FR-03 | 판정 순서를 고정한다: KB 없음 404 → 읽기 권한 없음 403 → 문서 없음 또는 다른 KB 소속 404 → 삭제 권한 없음 403 → 요약 잡 진행 중 409 → 삭제 실행. | High | Pending |
| FR-04 | KB 경로는 Qdrant와 ES 삭제가 모두 성공한 뒤에만 메타데이터를 지운다. 저장소 실패 시 메타데이터와 잡 행을 유지하고 재시도 가능한 5xx를 반환한다. 재시도는 멱등이어야 한다. | High | Pending |
| FR-05 | 요약 잡이 `pending`/`processing`이고 `SectionSummaryJobPolicy.is_stale()`이 거짓이면 409를 반환한다. stale 잡은 막지 않는다. | High | Pending |
| FR-06 | 저장소 삭제 성공 후 `section_summary_job` 행을 지운다. 문서 삭제 인터페이스를 잡 저장소에 추가한다. | Medium | Pending |
| FR-07 | 삭제 성공을 활동 로그(`DELETE_DOCUMENT`)에 `kb_id`와 함께 남긴다. 기존과 같이 로그 실패는 삭제 결과에 영향을 주지 않는다. | Medium | Pending |
| FR-08 | `GET /{kb_id}/documents` 응답의 문서 항목에 `can_delete: bool`을 추가한다(additive). 서버가 FR-02 정책으로 계산한다. | High | Pending |
| FR-09 | 컬렉션 문서 삭제 DELETE 2개를 `get_current_user`로 전환하고 헤더 파라미터를 제거한다. 미인증은 401이다. 기존 권한 정책과 ES 관대 처리는 유지한다. | High | Pending |
| FR-10 | KB 문서 표의 `can_delete=true` 행에 삭제 버튼을 둔다. 클릭이 행 드릴다운으로 전파되지 않아야 한다. | High | Pending |
| FR-11 | 공통 `ConfirmDialog`로 파일명과 복구 불가 사실을 안내한다. 대기 중 이중 제출을 막고, 409·403·5xx의 서버 메시지를 다이얼로그에 표시한다. | High | Pending |
| FR-12 | 성공 시 `queryKeys.knowledgeBases.all`을 invalidate하고, 삭제한 문서가 `selectedDoc`·`searchScopeDoc`이면 해제한다. | High | Pending |
| FR-13 | `api.ts`, `types/knowledgeBase.ts`, `knowledgeBaseService`, `useKnowledgeBases`를 백엔드 계약과 동기화한다. | High | Pending |

### 3.2 Non-Functional Requirements

| 범주 | 기준 | 측정 방법 |
|------|------|-----------|
| 보안 | 삭제 경로 3개 모두 토큰 인증을 거치며 헤더로 신원·역할을 주입할 수 없다 | 401 실요청 테스트, 위조 헤더 무시 테스트 |
| 데이터 정합성 | 성공 후 해당 `document_id`의 Qdrant·ES 포인트, 메타, 잡 행 0건. 다른 문서·같은 컬렉션 다른 KB 문서는 그대로 | 실저장소 스모크 |
| 성능 | 요청마다 Qdrant·ES 클라이언트를 만들지 않는다 | 앱 수명 싱글턴 재사용, DI 코드 확인 |
| 아키텍처 | 권한 규칙은 domain, 흐름은 application, 라우터는 예외 매핑만 맡는다. 함수 40줄·if 2단 이내 | `verify-architecture`, `verify-logging`, `verify-tdd` |
| 호환성 | 기존 KB 조회·업로드·컬렉션 화면 동작 불변. API 변경은 additive(FR-09 제외) | 회귀 FAILED 목록 diff |
| 접근성 | 삭제 버튼에 문서명이 포함된 접근 가능한 이름. 키보드로 조작 가능 | RTL `getByRole` 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 실 MySQL·Qdrant·ES에서 문서 삭제 후 해당 `document_id`의 메타·청크·요약·잡 행이 0건이고, 같은 컬렉션의 다른 KB 문서는 그대로다.
- [ ] SC-2: 권한 표(ADMIN, KB 소유자, 업로더, 다른 부서원, PUBLIC 열람자, 다른 KB 문서)가 각각 기대 상태 코드를 반환한다.
- [ ] SC-3: ES 삭제 실패 시 메타데이터가 유지되고 5xx를 반환하며, 복구 후 같은 요청이 성공한다.
- [ ] SC-4: 진행 중 요약 잡이 있으면 409이고, stale 잡은 삭제된다.
- [ ] SC-5: 컬렉션 삭제 API를 토큰 없이 `X-User-Role: admin`으로 호출하면 401이다. 토큰이 있는 기존 화면 삭제는 계속 동작한다.
- [ ] SC-6: KB 상세 화면에서 업로드 → 삭제 → 목록 감소 → 드릴다운·검색 범위 해제까지 실제 브라우저에서 확인한다. DB·Swagger 조작은 0회다.
- [ ] SC-7: 삭제 후 해당 KB의 리트리버 테스트 결과에 삭제한 문서가 나오지 않는다.

### 4.2 Quality Criteria

- [ ] 백엔드·프론트 모두 테스트를 먼저 작성한다(Red → Green → Refactor).
- [ ] 회귀는 통과 개수가 아니라 master 대비 정렬된 `FAILED` 목록 diff로 증명한다.
- [ ] 라우트는 TestClient 실요청으로 검증한다. DI 배선은 계약 테스트 또는 실런으로 확인한다.
- [ ] 프론트는 `npm run test:run`, `npm run lint`, `tsc -b`, `npm run build`를 통과한다.
- [ ] Protocol·ABC에 선언되지 않은 메서드 호출이 없도록 포트에 메서드를 먼저 추가한다.

---

## 5. Risks and Mitigation

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| 권한 판정 오류로 타인의 문서 삭제 | High | Medium | 가드 통과만으로 삭제하지 않는다. FR-02를 domain 정책 단위 테스트로 표 전체 검증하고, FR-03 순서를 라우터 실요청으로 고정한다. |
| Qdrant 성공 후 ES 실패로 부분 삭제 | High | Medium | 메타데이터를 마지막에 지워 재시도 경로를 유지한다. 재시도는 없는 데이터에 대한 삭제이므로 멱등이다. 재시도 전까지 벡터 검색과 키워드 검색 결과가 어긋날 수 있음을 허용한다. |
| 공유 `DeleteDocumentUseCase` 변경이 컬렉션 경로에 영향 | High | Medium | 컬렉션 경로의 관대한 ES 처리와 권한 판정을 기본 동작으로 유지하고, 엄격 삭제는 KB 경로에서만 선택한다. 기존 `test_delete_document_use_case.py`를 변경 없이 통과시킨다. |
| 요약 잡 경합: 진행 중 검사와 삭제 사이에 재시도가 시작 | Medium | Low | 재시도 API가 같은 시간창에 호출될 때만 발생한다. 잠금은 도입하지 않고 고아 요약 위험을 문서화한다. |
| 인증 전환 후 컬렉션 삭제 동작 변화 | Medium | Medium | 프론트는 이미 `authApiClient`로 토큰을 보낸다. 다만 지금까지 `X-User-Role`을 보내지 않아 ADMIN도 일반 사용자로 판정되었으므로, 전환 후 ADMIN의 삭제 범위가 넓어진다. 의도된 변경으로 보고서에 기록한다. |
| `doc_browse_router` GET 2개 미인증 잔존 | High | High | 이번 범위 밖이다. 문서 목록·청크 원문이 미인증으로 조회될 수 있으므로 후속 소형 사이클을 Report에 이월한다. |
| `user_id`가 비어 있는 과거 문서 | Low | Low | 업로더 판정이 거짓이 되어 소유자·ADMIN만 삭제할 수 있다. 안전한 방향이므로 그대로 둔다. |
| 실저장소 없이 Do 종료 | High | Medium | SC-1·SC-3·SC-6은 실런을 요구한다. 저장소를 띄울 수 없으면 완료로 표기하지 않고 E2E 이월로 명시한다. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| 자원 | 유형 | 변경 내용 |
|------|------|-----------|
| `knowledge_base_router.py` | API | DELETE 1개 추가, 문서 목록 응답에 `can_delete` 추가 |
| `KnowledgeBasePolicy` | Domain | 문서 삭제 판정 추가 |
| `ListKbDocumentsUseCase` | Application | 문서별 `can_delete` 계산 |
| 신규 KB 문서 삭제 UseCase | Application | 가드, 권한, 잡 검사, 저장소 삭제를 조립 |
| `DeleteDocumentUseCase` | Application | 권한 검사를 끝낸 호출자용 엄격 삭제 진입점 추가 |
| `SectionSummaryJobStoreInterface`와 구현체 | Domain/Infra | `document_id` 기준 행 삭제 추가 |
| `doc_browse_router.py` DELETE 2개 | API | 헤더 인증 → `get_current_user` (Breaking: 미인증 호출 차단) |
| `main.py` | DI | 신규 UseCase 배선 |
| KB 프론트 타입·서비스·훅·표·페이지 | Frontend | §3 FR-10~13 |

스키마 변경은 없다. 마이그레이션 0건이다.

### 6.2 Current Consumers

| 자원 | 작업 | 코드 경로 | 영향 |
|------|------|-----------|------|
| 컬렉션 DELETE 2개 | DELETE | `collectionService.deleteDocument(s)` → `useCollections` → `CollectionDocumentsPage` | 토큰 전송 중이라 호환. ADMIN 범위 확대(§5) |
| `DeleteDocumentUseCase.execute_single/batch` | DELETE | `doc_browse_router.py:148,178` | 메서드 불변 |
| `KbDocumentInfoResponse` | READ | `useKbDocuments` → `KbDocumentTable`, `KbStatusCards` | 필드 추가만. 영향 없음 |
| `ListKbDocumentsUseCase` | READ | `knowledge_base_router.py:454`, `test_list_documents_use_case.py` | 사용자 권한 계산 추가. 픽스처 확인 필요 |
| `KbDocumentTable` props | READ | `KnowledgeBaseDetailPage`, `KbDocumentTable.test.tsx` | 선택 prop 추가. 기존 테스트 불변 |
| `section_summary_job` | READ/UPDATE | 조회·재시도·러너 | 삭제 후 404 흐름 확인 필요. 진행 중 잡은 409로 삭제되지 않음 |
| `document_metadata` | READ | KB 목록, 관리자 대시보드 집계, 컬렉션 문서 목록 | 삭제분이 집계에서 빠짐(기대 동작) |
| `search_history`, `ai_run` 계열 `document_id` | READ | 검색 이력, 실행 관측 | 이력 보존. 삭제된 문서를 가리킬 수 있음(기존 소프트 참조) |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후 동작한다.
- [ ] 인증 전환이 `CollectionDocumentsPage` 삭제를 깨지 않는다.
- [ ] 필드 추가가 기존 조회·뮤테이션을 깨지 않는다.

---

## 7. Architecture Considerations

### 7.1 Project Level

기존 구조를 따른다. 백엔드는 Thin DDD(domain → application → infrastructure → interfaces), 프론트는 React SPA 구조다.

### 7.2 Key Architectural Decisions

| 결정 | 선택지 | 선택 | 근거 |
|------|--------|------|------|
| 삭제 권한 | 업로드 권한자 전원 / 소유자·ADMIN / 소유자·ADMIN·업로더 | 소유자·ADMIN·업로더 | 본인 실수를 되돌리면서 부서원이 남의 문서를 지우지 못하게 한다. 사용자 결정 |
| 요약 잡 경합 | 409 차단 / 취소 플래그 / 고아 감수 | 409 차단(stale 제외) | 러너를 고치지 않는다. 사용자 결정 |
| 부분 실패 | 메타 유지·재시도 / 기존 동작+경고 | 메타 유지·재시도 | 재시도 경로가 있어야 DB 조작 없이 복구된다. 사용자 결정 |
| 위임 방식 | 기존 메서드 호출 / 호출자 검증 전제 진입점 분리 | 진입점 분리(세부는 Design) | 컬렉션 정책이 KB 소유자를 거부할 수 있고, 컬렉션 경로 동작을 유지해야 한다 |
| 버튼 노출 판단 | 프론트 재계산 / 서버 계산 필드 | 서버 `can_delete` | 부서 소속·업로더 정보를 프론트가 온전히 알 수 없고 규칙 중복을 피한다 |
| 삭제 순서 | - | Qdrant → ES → 잡 행 → 메타 | 메타가 재시도 진입점이므로 마지막에 지운다 |
| 클라이언트 | 요청별 생성 / 앱 싱글턴 | 앱 싱글턴 재사용 | 기존 팩토리의 요청별 생성은 위키 패턴에 어긋난다. 신규 경로는 싱글턴을 쓴다 |
| 프론트 UI | 공통 키트 | `ConfirmDialog`, `IconButton` 또는 `Button` | 신규 코드는 디자인 토큰을 쓴다. 기존 표 전체 재작성은 하지 않는다 |

### 7.3 구조 미리보기

```
idt/src/
├── domain/knowledge_base/policy.py                     (문서 삭제 판정)
├── domain/section_summary/interfaces.py                (문서 기준 잡 삭제)
├── application/knowledge_base/delete_document_use_case.py  (신규)
├── application/knowledge_base/list_documents_use_case.py   (can_delete)
├── application/doc_browse/delete_document_use_case.py      (엄격 삭제 진입점)
├── infrastructure/section_summary/                     (잡 삭제 구현)
├── api/routes/knowledge_base_router.py                 (DELETE, 응답 필드)
├── api/routes/doc_browse_router.py                     (인증 전환)
└── api/main.py                                         (DI)

idt_front/src/
├── constants/api.ts · types/knowledgeBase.ts
├── services/knowledgeBaseService.ts · hooks/useKnowledgeBases.ts
├── components/knowledge-base/KbDocumentTable.tsx
├── components/knowledge-base/DeleteKbDocumentDialog.tsx  (신규)
└── pages/KnowledgeBaseDetailPage/index.tsx
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종과 `idt/docs/rules/`
- [x] ESLint, TypeScript 설정
- [x] 프론트 디자인 토큰과 공통 키트

### 8.2 Conventions to Verify

| 범주 | 현재 상태 | 이번 적용 | 우선순위 |
|------|-----------|-----------|----------|
| DB 세션 | `docs/rules/db-session.md` | Repository에서 commit 금지, UseCase 내 단일 세션 | High |
| 잡 저장소 | 메서드별 단기 세션 | 신규 삭제 메서드도 같은 방식인지 Design에서 확인 | High |
| 로깅 | `docs/rules/logging.md` | `request_id` 포함, 실패는 `exception=e` | High |
| 에러 매핑 | `_raise_http`는 문자열 "not found"·"already exists" 기준 | 409·5xx 매핑 방식을 Design에서 결정 | High |
| 프론트 에러 | `authApiClient`는 `ApiError`로 변환 | `err.response`가 아닌 `ApiError.message` 사용 | Medium |
| 프론트 상수 | 컴포넌트 파일의 런타임 export 금지 | 공유 상수는 `src/types` 또는 `src/constants` | Medium |

### 8.3 Environment Variables Needed

추가 환경변수는 없다.

### 8.4 Pipeline Integration

9단계 파이프라인 대상이 아니다. PDCA 사이클만 수행한다.

---

## 9. Next Steps

1. [ ] `/pdca design kb-document-management`: 위임 구조, 에러 매핑, 응답 스키마, 테스트 계획 확정
2. [ ] 사용자 검토 후 Do 단계 착수
3. [ ] Report에 후속 이월: `doc_browse_router` GET 인증, `kb-vector-cleanup`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | 초안 작성. 범위·권한·경합·부분 실패 결정 반영 | 배상규 + Claude |
