# kb-management-ui Design — 지식베이스 관리 화면

> **Status**: Design
> **Date**: 2026-07-10
> **Plan**: `docs/01-plan/features/kb-management-ui.plan.md`
> **범위**: 프론트 `/knowledge-bases` 목록·생성·삭제·상세(문서 목록)·업로드 + 백엔드 KB 문서 목록 API 1건

---

## 1. 설계 개요

Plan Q1~Q4 확정에 따라, 백엔드는 **FR-08(KB 문서 목록) 1건만 신규**이고 나머지는 기존 API 소비다.
프론트는 CollectionPage/CollectionDocumentsPage 선례를 그대로 복제한다(페이지가 모달 상태 소유, 공용 `Modal`/`ConfirmDialog`/`Dropdown`, react-query 훅 + queryKeys, 인라인 에러 — toast 없음).

## 2. As-Is 조사 근거 (2026-07-10 코드 확인)

| 사실 | 근거 | 설계 귀결 |
|------|------|-----------|
| 문서 목록의 진실 소스 = MySQL `document_metadata` (doc_browse는 이 테이블 조회) | `list_documents_use_case.py` → `DocumentMetadataRepositoryInterface.find_by_collection` | FR-08도 같은 소스 사용 (D1) |
| `document_metadata`에 **kb_id 컬럼 없음** | `infrastructure/doc_browse/models.py` | V047 additive 컬럼 필요 (D1) |
| KB 업로드는 `extra_metadata={kb_id, kb_name}`을 unified upload에 위임하지만, `DocumentMetadata` 저장 시 kb_id **누락** | `knowledge_base/upload_use_case.py:83`, `unified_upload/use_case.py:132-141` | 업로드 기록 확장 (D2) |
| ES 청크 문서에는 filename·업로드시각의 문서 단위 표현이 없고 집계 페이지네이션 부적합 | `_store_to_es` (청크 단위 저장) | ES 집계안 기각 (D1 대안) |
| KB 권한 판정 기존 자산: `KnowledgeBasePolicy.can_read`, 라우터 `_raise_http`(403/404/409/422) | `knowledge_base/use_case.py`, `knowledge_base_router.py` | FR-08 권한/에러 재사용 (D3) |
| 프론트: 공용 `Modal`/`ConfirmDialog`/`Dropdown`, `useDepartments`, `COLLECTION_ERROR_MAP` 패턴, MSW per-file 훅 | Explore 조사 (CollectionPage 등) | §5 컴포넌트 설계 |
| `queryKeys.knowledgeBases {all, list}` + `useKnowledgeBases` + `KnowledgeBaseInfo`(축약형) 기존 존재 | kb-rag-filter 산출물 | additive 확장, 이동 금지 (D5) |
| 업로드 선례: FormData + `timeout: 120_000`, 진행률 없는 스피너 | `unifiedUploadService.ts`, `UploadDocumentModal.tsx` | KB 업로드 동일 패턴 (D6) |
| 마이그레이션 최신 V046 | `db/migration/` | 신규 = **V047** |

## 3. 결정사항 (D1~D8)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | FR-08 데이터 소스 = **MySQL `document_metadata` + `kb_id` nullable 컬럼(V047)**. ES 집계안 기각 | 문서 목록 진실 소스 일관성(기존 doc_browse와 동일), filename/created_at 보유, LIMIT/OFFSET 페이지네이션 무료. ES는 청크 단위라 문서 표현·페이지네이션 부적합 |
| **D2** | 기록 지점 = `UnifiedUploadUseCase`의 `DocumentMetadata` 저장 시 `kb_id=request.extra_metadata.get("kb_id")` | KB 업로드가 이미 extra_metadata로 kb_id를 흘리고 있음 — 추가 배선 0. 일반 업로드(extra_metadata에 kb_id 없음)는 NULL로 기존 동작 불변 |
| **D3** | FR-08 권한 = **`KnowledgeBaseUseCase.get()` 선행 호출로 위임** (can_read 검증 + 미존재 ValueError) → 신규 UseCase는 목록 조회만 담당 | 권한 규칙 중복 구현 금지 — get()이 이미 403/404 계약을 보유, 라우터 `_raise_http` 그대로 매핑 |
| **D4** | 기존 KB 업로드 문서(kb_id NULL) backfill은 **비범위** — 목록에 미표시됨을 알려진 한계로 명기 | knowledge-base-scoping E2E 미수행 상태라 실데이터 사실상 없음. 필요 시 후속 1회성 스크립트(ES kb_id→document_id 추출) |
| **D5** | 프론트 타입: `KnowledgeBaseInfo`는 `types/ragToolConfig.ts`에 **그대로 두고 optional 필드만 additive 확장**, 관리 화면 전용 타입은 신규 `types/knowledgeBase.ts` | kb-rag-filter 컴포넌트들의 import 경로 무수정(무회귀). 독립 opt-in 원칙 |
| **D6** | 업로드 UI = `UploadDocumentModal` 선례 복제: FormData + timeout 120s + 상태 머신(idle/loading/success/partial/error) + `StorageResultCard` 동형 결과 표시. child_chunk_* 파라미터는 **노출 안 함**(백엔드 기본값) | KB가 clause chunking이면 해당 파라미터는 무시됨(백엔드 D6) — 노출하면 오해 유발. 진행률 없는 스피너는 기존 UX와 동일 |
| **D7** | 사이드바 active 판정은 이 항목만 `startsWith('/knowledge-bases')` | 상세 라우트(`/knowledge-bases/:kbId`)에서도 항목 활성 유지 — admin 버튼 `startsWith` 선례 |
| **D8** | 삭제 버튼 노출 = `kb.owner_id === Number(user.id) \|\| user.role === 'admin'` (클라이언트 gating은 표시용, 실권한은 백엔드 403) | CollectionTable의 currentUserId/Role gating 선례. KbInfoResponse가 owner_id 제공 |

## 4. 백엔드 설계 (idt/)

### 4.1 V047 마이그레이션

```sql
-- V047__alter_document_metadata_add_kb_id.sql
ALTER TABLE document_metadata
    ADD COLUMN kb_id VARCHAR(64) NULL DEFAULT NULL,
    ADD INDEX idx_dm_kb (kb_id);
```
(ENGINE/COLLATE 명시 금지 — V037 주석 선례. FK 없음: KB soft-delete와 독립)

### 4.2 도메인 (src/domain/doc_browse/)

- `schemas.py` — `DocumentMetadata`에 `kb_id: Optional[str] = None` additive.
  신규 `@dataclass(frozen=True) KbDocumentSummary(document_id, filename, chunk_count, chunk_strategy, created_at: Optional[datetime])`.
- `interfaces.py` — `DocumentMetadataRepositoryInterface.find_by_kb_id(kb_id, request_id, pagination) -> Page[KbDocumentSummary]` 추상 메서드 추가.

### 4.3 인프라 (src/infrastructure/doc_browse/)

- `models.py` — `kb_id = Column(String(64), nullable=True)` + `Index("idx_dm_kb", "kb_id")`.
- `document_metadata_repository.py` — `save()`에 kb_id 반영, `find_by_kb_id()` 구현(kb_id equality + created_at DESC + LIMIT/OFFSET, count 병행). 세션 규칙: 기존 메서드와 동일(commit 금지).

### 4.4 애플리케이션 (src/application/)

- `unified_upload/use_case.py` — `DocumentMetadata(... kb_id=request.extra_metadata.get("kb_id"))` 1줄 (D2).
- 신규 `knowledge_base/list_documents_use_case.py`:
  ```python
  class ListKbDocumentsUseCase:
      def __init__(self, kb_use_case: KnowledgeBaseUseCase,
                   document_metadata_repo, logger): ...
      async def execute(self, kb_id, user, request_id,
                        offset=0, limit=20) -> KbDocumentListResult:
          kb = await self._kb_use_case.get(kb_id, user, request_id)  # D3: 403/404 위임
          page = await self._repo.find_by_kb_id(kb_id, request_id, pagination)
          return KbDocumentListResult(kb_id, kb.name, documents, total, offset, limit)
  ```

### 4.5 인터페이스 (src/api/routes/knowledge_base_router.py)

```
GET /api/v1/knowledge-bases/{kb_id}/documents?offset=0&limit=20
→ 200 KbDocumentListResponse {
    kb_id, kb_name,
    documents: [{document_id, filename, chunk_count, chunking_strategy, created_at}],
    total, offset, limit
  }
→ 403 (can_read 실패) / 404 (미존재) — 기존 _raise_http 재사용
```
DI: `main.py`에 `ListKbDocumentsUseCase` 팩토리(동일 세션에서 kb 관련 repo 구성 — 기존 `get_knowledge_base_use_case` 팩토리 선례).

### 4.6 무변경 명시

- KB CRUD/업로드/섹션요약 엔드포인트, doc_browse 기존 API, `find_by_collection` — 무수정.
- `DocumentMetadata.kb_id` 기본 None → 일반 업로드·기존 테스트 전건 불변.

## 5. 프론트엔드 설계 (idt_front/)

### 5.1 타입 (D5)

- `types/ragToolConfig.ts` — `KnowledgeBaseInfo`에 optional additive: `owner_id?: number; use_clause_chunking?: boolean; created_at?: string | null;`
- 신규 `types/knowledgeBase.ts`:
  `CreateKnowledgeBaseRequest {name, description?, scope, department_id?, collection_name, use_clause_chunking?}` ·
  `KbCreateResponse` · `KbDocumentInfo {document_id, filename, chunk_count, chunking_strategy, created_at}` ·
  `KbDocumentListResponse` · `KbUploadResponse`(백엔드 계약 미러: qdrant/es 상태, section_summary?).

### 5.2 상수/서비스/훅

- `constants/api.ts` — `KNOWLEDGE_BASE_DETAIL: (id) => \`/api/v1/knowledge-bases/${id}\``, `KNOWLEDGE_BASE_DOCUMENTS: (id) => \`...(id)/documents\`` (COLLECTION_* 팩토리 선례).
- `services/knowledgeBaseService.ts` — 기존 `getKnowledgeBases` 유지 + `getKnowledgeBase(kbId)`, `createKnowledgeBase(body)`, `deleteKnowledgeBase(kbId)`, `getKbDocuments(kbId, {offset, limit})`, `uploadKbDocument(kbId, file)`(FormData, `authApiClient`, timeout 120_000).
- `lib/queryKeys.ts` — `knowledgeBases`에 `detail: (id)`, `documents: (id, params)` 추가 (`.all` spread 관례).
- `hooks/useKnowledgeBases.ts` — 기존 `useKnowledgeBases()` 유지 + `useKnowledgeBase(kbId)`, `useKbDocuments(kbId, paging)`, `useCreateKnowledgeBase()`, `useDeleteKnowledgeBase()`, `useUploadKbDocument(kbId)` — mutation `onSuccess`에서 `invalidateQueries({queryKey: queryKeys.knowledgeBases.all})` (agent-builder 드롭다운 자동 동기화 = FR-07).

### 5.3 페이지/컴포넌트

```
src/pages/KnowledgeBasesPage/index.tsx        — 목록 + 생성/삭제 모달 상태 소유
src/pages/KnowledgeBaseDetailPage/index.tsx   — useParams kbId, 정보 헤더 + 문서 목록 + 업로드 모달
src/components/knowledge-base/
  KnowledgeBaseTable.tsx        — 이름(상세 링크)·scope 배지·설명·컬렉션·생성일·삭제 버튼(D8)
  CreateKnowledgeBaseModal.tsx  — 이름/설명/scope Dropdown/부서 Dropdown(DEPARTMENT 시, useDepartments)/
                                  컬렉션 Dropdown(useCollectionList, 빈 목록 시 안내문 R2)/
                                  고급 접기: use_clause_chunking 토글 · 인라인 에러(KB_ERROR_MAP)
  DeleteKnowledgeBaseDialog.tsx — ConfirmDialog 래퍼(variant danger, soft-delete 안내문)
  KbDocumentTable.tsx           — 파일명·청크 수·전략·업로드일 (+빈 목록 안내)
  KbUploadDocumentModal.tsx     — UploadDocumentModal 동형(D6): 파일 선택→loading→결과
                                  (chunk_count/strategy/Qdrant·ES StorageResultCard/
                                   section_summary 있으면 "요약 생성 중" 뱃지)
```
- 에러 매핑: `KB_ERROR_MAP = {403: '권한이 없습니다', 404: '지식베이스를 찾을 수 없습니다', 409: '같은 이름의 지식베이스가 이미 있습니다', 422: '입력값을 확인해주세요(부서/컬렉션)'}` (COLLECTION_ERROR_MAP 선례).
- scope 배지 라벨/스타일: 기존 `SCOPE_LABELS`(`@/types/collection` — 개인/부서/**공개**) 재사용 — 컬렉션 화면과 시각 언어 통일 (Check Gap 1 정정: 코드가 진실 소스).

### 5.4 라우팅/내비

- `App.tsx` — `AgentChatLayout` 아래 `/knowledge-bases`, `/knowledge-bases/:kbId` 2개 라우트 (정적 import, `/collections` 옆).
- `AppSidebar.tsx` — `BOTTOM_ITEMS` '리소스' 옆에 `{label: '지식베이스', path: '/knowledge-bases', iconPath: ...}` 추가, active는 `startsWith` (D7).

## 6. 테스트 목록 (TDD — 테스트 먼저)

### 백엔드 (pytest)

| 파일 | 케이스 |
|------|--------|
| `tests/application/knowledge_base/test_list_documents_use_case.py` (신규) | ① 정상 목록 반환(kb_name 포함) ② 타 KB 문서 미포함(kb_id 필터 — repo 호출 인자 검증) ③ 읽기권한 없음 → PermissionError ④ 미존재 kb → ValueError(not found) ⑤ 페이지네이션 파라미터 전달 ⑥ 빈 목록 |
| `tests/application/unified_upload/…` (기존 파일 확장) | ⑦ extra_metadata에 kb_id 있으면 DocumentMetadata.kb_id 저장 ⑧ 없으면 None(기존 경로 불변) |
| `tests/infrastructure/doc_browse/…` (기존 관례 따라) | ⑨ find_by_kb_id 쿼리 구성(필터+정렬+페이지) — 기존 repo 테스트 스타일 있으면 동형, 없으면 생략 가능 |

### 프론트엔드 (Vitest + RTL + MSW, per-file server 훅 + `--pool=threads`)

| 파일 | 케이스 |
|------|--------|
| `pages/KnowledgeBasesPage/index.test.tsx` (신규) | ① 목록 렌더(scope 배지) ② 빈 목록 안내 ③ 생성 성공 → 모달 닫힘+목록 갱신 ④ 409 중복 이름 인라인 에러 ⑤ 삭제 확인 → 성공 ⑥ 비소유자 삭제 버튼 미노출(D8) |
| `components/knowledge-base/CreateKnowledgeBaseModal.test.tsx` (신규) | ⑦ DEPARTMENT 선택 시 부서 Dropdown 노출 ⑧ 컬렉션 빈 목록 안내(R2) ⑨ 고급 접기 토글 값 제출 반영 |
| `pages/KnowledgeBaseDetailPage/index.test.tsx` (신규) | ⑩ KB 정보+문서 목록 렌더 ⑪ 업로드 성공 → 결과(청크 수·Qdrant/ES 상태) 표시 ⑫ 업로드 중 닫기 차단(disableClose) ⑬ section_summary 있으면 요약 뱃지 |
| 회귀 | `RagConfigPanel.test.tsx`·`useKnowledgeBases.test.ts` 기존 그린 유지(무수정) |

MSW 핸들러: `__tests__/mocks/handlers.ts`에 KB detail/documents/create/delete/upload 기본 핸들러 추가(기존 KB 목록 핸들러 옆).

## 7. 구현 순서

1. **BE-1**: V047 + 도메인 스키마/인터페이스 + 모델/레포 (⑨) + unified upload kb_id 기록 (⑦⑧)
2. **BE-2**: `ListKbDocumentsUseCase` (①~⑥) + 라우터 엔드포인트 + main.py DI
3. **FE-1**: 타입/상수/서비스/queryKeys/훅 확장 + MSW 핸들러
4. **FE-2**: 목록 페이지 + 생성 모달 + 삭제 다이얼로그 (①~⑨)
5. **FE-3**: 상세 페이지 + 문서 테이블 + 업로드 모달 (⑩~⑬)
6. **FE-4**: App.tsx 라우트 + AppSidebar 항목 + 회귀 확인(tsc, RagConfigPanel)
7. **[E2E 수동]**: 백엔드+Qdrant/ES 기동 → KB 생성→업로드→agent-builder 드롭다운 노출→검색 격리 (kb-rag-filter G2와 묶어 실측)

## 8. 수용 기준 (Plan §7 매핑)

- [ ] 백엔드 ①~⑧ Green + 기존 doc_browse/unified_upload/knowledge_base 스위트 회귀 0
- [ ] 프론트 ①~⑬ Green + RagConfigPanel 회귀 0 + tsc 신규 에러 0
- [ ] V047 적용 문서화(배포 전 필수 목록)
- [ ] 알려진 한계 명기: kb_id NULL 기존 문서 미표시(D4), 섹션요약 진행률 폴링 없음(후속)

## 9. 영향 범위 / 주의

- `document_metadata` 스키마 additive 변경 — 배포 전 V047 적용 필수. 일반 업로드 경로는 kb_id NULL로 동작 불변.
- `unified_upload/use_case.py` 1줄 수정이 유일한 기존 코드 변경(백엔드) — 회귀 테스트 ⑧로 고정.
- 프론트 신규 파일 위주 + 기존 파일 4곳(타입 additive, 서비스/훅/queryKeys 확장, App/사이드바) — kb-rag-filter 산출물 이동/이름변경 금지(D5).
