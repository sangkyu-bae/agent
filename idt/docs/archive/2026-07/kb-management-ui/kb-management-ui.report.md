# kb-management-ui 완료 보고서

> **Feature**: 지식베이스 관리 화면 (`/knowledge-bases` 독립 페이지)
>
> **Completed**: 2026-07-10
> **Status**: ✅ Completed (96.9% Match Rate, 0 iterations)

---

## Executive Summary

| 항목 | 값 |
|------|-----|
| **Feature** | 지식베이스(KB) 관리 화면 — `/knowledge-bases` 독립 페이지 (목록·생성·삭제·상세 문서 목록·문서 업로드) |
| **기간** | 2026-07-10 (1일 사이클) |
| **Owner** | sangkyu-bae |
| **Match Rate** | 93.8% → **96.9%** (31 / 32, Check 내 3건 즉시 해소) |
| **Iteration** | 0회 (Act 불필요) |

### 1.1 결과 요약

**백엔드 (idt/)**
- 신규 API: `GET /api/v1/knowledge-bases/{kb_id}/documents` (KB 문서 목록 필터)
- V047 마이그레이션: `document_metadata` 테이블에 `kb_id nullable` 컬럼 + 인덱스
- 테스트: 신규 12건 (UseCase 6 + 업로드 kb_id 2 + repository 4) + 회귀 506건 통과, 53건 기지 Windows 이벤트루프 이슈(격리 실행 확인)

**프론트엔드 (idt_front/)**
- 신규 페이지 2 (KnowledgeBasesPage + KnowledgeBaseDetailPage)
- 신규 컴포넌트 5 (Table, CreateModal, DeleteDialog, DocumentTable, UploadModal)
- 서비스/훅/queryKeys/타입 확장
- 테스트: 신규 15건 + 회귀 20건 + tsc 0 에러

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 백엔드 KB CRUD/업로드 API는 완비됐지만, 사용자가 KB를 *만들고 문서를 넣는* UI가 없어 일반 사용자는 KB 기능(agent-builder 검색 격리)을 실사용할 수 없었음 |
| **Solution** | 독립 페이지 `/knowledge-bases` 신설(사이드바 추가): KB 목록·생성·삭제 + 상세(문서 목록·업로드). 백엔드는 kb_id 필터 문서 목록 API 1건만 추가, 나머지는 기존 API 소비 |
| **Function/UX Effect** | KB 생성(이름·설명·scope·컬렉션·조항청킹 토글) → 문서 업로드 → 결과(청크 수·저장 상태·요약 잡 킥오프) 즉시 확인. agent-builder에서 그 KB를 선택해 검색 범위 격리하는 전체 흐름이 UI로 완성 |
| **Core Value** | "문서 물리 관리(관리자) → 논리 조직화(사용자) → 에이전트 검색 격리" 파이프라인의 사용자 진입점 완성 — 단일 컬렉션 전환 로드맵의 전제 조건 |

---

## PDCA 단계별 여정

### Plan (2026-07-10)

**입력**:
- knowledge-base-scoping (백엔드 KB 계층 완성)
- kb-rag-filter (agent-builder KB 선택 드롭다운 완성)

**확정 결정 4건** (사용자 확인):
1. **화면 범위**: 목록·생성·삭제 + 문서 업로드 (섹션요약 진행률/재시도 UI는 후속)
2. **수정 제외**: rename 기능은 백엔드 PATCH API 부재로 비범위 → 후속 `kb-rename`
3. **청킹 옵션**: `use_clause_chunking` 토글만 노출 (프로파일 목록은 admin 전용)
4. **위치**: 독립 페이지 `/knowledge-bases` + 사이드바 항목

**위험 식별**:
- R1: 업로드 동기 처리(파싱+임베딩) — 대용량 PDF 수십 초 지연 → 명시적 스피너+안내로 대응
- R2: 컬렉션 없는 사용자는 KB 생성 불가 → 생성 폼에 안내 문구
- R3: FR-08 집계 성능 → ES `kb_id` keyword 매핑 기존 반영(knowledge-base-scoping)
- R4: Windows 테스트 환경 → 기지 사항 (vitest `--pool=threads`, MSW per-file 훅)

### Design (2026-07-10)

**설계 원칙**: CollectionPage/CollectionDocumentsPage 선례 복제로 프론트 편차 최소화

**핵심 결정 8건 (D1~D8)**:

| 결정 | 내용 | 근거 |
|------|------|------|
| **D1** | FR-08 데이터 소스 = MySQL `document_metadata` + `kb_id` nullable 컬럼(V047) | 문서 목록 진실 소스 일관성, filename/created_at 보유, 페이지네이션 지원. ES는 청크 단위라 부적합 |
| **D2** | 기록: `UnifiedUploadUseCase` → `kb_id=request.extra_metadata.get("kb_id")` | KB 업로드가 이미 extra_metadata로 kb_id 흘림. 일반 업로드는 NULL로 기존 동작 불변 |
| **D3** | 권한: `KnowledgeBaseUseCase.get()` 선행 호출로 위임 (can_read 검증) | 권한 규칙 중복 구현 금지 — get()이 이미 403/404 계약 보유 |
| **D4** | 기존 KB NULL 문서 backfill = 비범위 | knowledge-base-scoping E2E 미수행 상태라 실데이터 사실상 없음. API description에 한계 명기 |
| **D5** | 프론트 타입: `KnowledgeBaseInfo` 제자리 optional 확장 + 신규 `types/knowledgeBase.ts` | kb-rag-filter 컴포넌트 import 경로 무수정(무회귀). 독립 opt-in 원칙 |
| **D6** | 업로드 UI = `UploadDocumentModal` 선례 복제: 상태머신 + 저장 상태 카드, child_chunk_* 미노출 | clause chunking이면 파라미터 무시됨. 노출하면 오해 유발 |
| **D7** | 사이드바 active = `startsWith('/knowledge-bases')` | 상세 라우트(`/knowledge-bases/:kbId`)에서도 항목 활성 유지 |
| **D8** | 삭제 버튼 = `owner_id === userId ∥ admin`, 비소유자 미노출 | 클라이언트 gating은 표시용, 실권한은 백엔드 403. CollectionTable 선례 |

**백엔드 설계**:
- V047: `ALTER TABLE document_metadata ADD COLUMN kb_id VARCHAR(64) NULL + INDEX idx_dm_kb`
- 신규 UseCase: `ListKbDocumentsUseCase` (권한 위임, 문서 목록만 담당)
- 신규 Endpoint: `GET /api/v1/knowledge-bases/{kb_id}/documents?offset=0&limit=20`

**프론트엔드 설계**:
- 페이지: `KnowledgeBasesPage` (목록, 모달 상태 소유), `KnowledgeBaseDetailPage` (상세, 문서 목록+업로드)
- 컴포넌트: `KnowledgeBaseTable`, `CreateKnowledgeBaseModal`, `DeleteKnowledgeBaseDialog`, `KbDocumentTable`, `KbUploadDocumentModal`

### Do (2026-07-10)

**구현 순서 7단계**:

1. **BE-1**: V047 + 도메인/인프라 (schema/model/repository)
   - ✅ `V047__alter_document_metadata_add_kb_id.sql`
   - ✅ `src/domain/doc_browse/schemas.py` — `DocumentMetadata.kb_id`, `KbDocumentSummary` VO
   - ✅ `src/infrastructure/doc_browse/models.py` — Column 추가 + 인덱스
   - ✅ `src/infrastructure/doc_browse/document_metadata_repository.py` — `find_by_kb_id()` 구현

2. **BE-2**: `ListKbDocumentsUseCase` + 라우터
   - ✅ `src/application/knowledge_base/list_documents_use_case.py`
   - ✅ `src/api/routes/knowledge_base_router.py` — 엔드포인트 추가
   - ✅ `src/api/main.py` — DI 팩토리 추가

3. **BE-3**: unified_upload kb_id 기록
   - ✅ `src/application/unified_upload/use_case.py` — 1줄 추가

4. **FE-1**: 타입/상수/서비스/훅 확장
   - ✅ `types/ragToolConfig.ts` — `KnowledgeBaseInfo` optional 필드 추가
   - ✅ `types/knowledgeBase.ts` (신규) — `CreateKnowledgeBaseRequest`, `KbDocumentInfo`, `KbDocumentListResponse`, `KbUploadResponse`
   - ✅ `constants/api.ts` — `KNOWLEDGE_BASE_DETAIL`, `KNOWLEDGE_BASE_DOCUMENTS`
   - ✅ `services/knowledgeBaseService.ts` — get/create/delete/getKbDocuments/uploadKbDocument
   - ✅ `lib/queryKeys.ts` — `knowledgeBases.detail`, `knowledgeBases.documents`
   - ✅ `hooks/useKnowledgeBases.ts` — 6개 훅 + mutation `.all` invalidate
   - ✅ `__tests__/mocks/handlers.ts` — KB 관련 MSW 핸들러

5. **FE-2**: 목록 페이지 + 생성/삭제
   - ✅ `pages/KnowledgeBasesPage/index.tsx` — 목록 + 모달 상태 소유
   - ✅ `components/knowledge-base/KnowledgeBaseTable.tsx` — 이름/scope/설명/컬렉션/생성일 + 삭제 버튼
   - ✅ `components/knowledge-base/CreateKnowledgeBaseModal.tsx` — 폼 + 검증
   - ✅ `components/knowledge-base/DeleteKnowledgeBaseDialog.tsx` — 확인 다이얼로그

6. **FE-3**: 상세 페이지 + 문서 목록 + 업로드
   - ✅ `pages/KnowledgeBaseDetailPage/index.tsx` — 상세 정보 + 문서 목록 + 업로드 모달
   - ✅ `components/knowledge-base/KbDocumentTable.tsx` — 문서 테이블
   - ✅ `components/knowledge-base/KbUploadDocumentModal.tsx` — 업로드 폼 + 결과

7. **FE-4**: 라우팅 + 사이드바 + 회귀
   - ✅ `App.tsx` — `/knowledge-bases`, `/knowledge-bases/:kbId` 라우트 추가
   - ✅ `AppSidebar.tsx` — '지식베이스' 항목 + `startsWith` active

### Check (2026-07-10)

**최초 판정**: 93.8% (30 / 32)

**Check 내 즉시 해소 3건**:

| Gap | 최초 판정 | 조치 | 결과 |
|-----|----------|------|------|
| **G1** | scope 배지 라벨 불일치 ('전체공개' vs 코드 '공개') + dead code | 설계 §5.3 정정: 기존 `SCOPE_LABELS` 재사용(코드=진실 소스) + dead code 제거 | Match |
| **G2** | DetailPage ⑫⑬ (disableClose, section_summary 뱃지) 미커버 | 지연 응답 핸들러 + 테스트 2건 추가 (DetailPage 4→6건) | Match |
| **Ref 5** | repo `save()` update 경로 kb_id 미반영 | `existing.kb_id = metadata.kb_id` 1줄 추가 (방어 보강) | Match |

**재검증**: 프론트 15건 + tsc 0, 백엔드 14건 + 회귀 506+53

**최종 판정**: **96.9%** (31 / 32)

### Act

**상태**: 불필요 (Match Rate 96.9% ≥ 90%, 0 iterations)

---

## 구현 상세

### 백엔드 (idt/)

**신규 파일**:
1. `db/migration/V047__alter_document_metadata_add_kb_id.sql` — KB 문서 필터링용 kb_id 컬럼
2. `src/domain/doc_browse/schemas.py` (확장) — `DocumentMetadata.kb_id: Optional[str]`, `KbDocumentSummary` VO
3. `src/infrastructure/doc_browse/document_metadata_repository.py` (확장) — `find_by_kb_id()` 구현
4. `src/application/knowledge_base/list_documents_use_case.py` — UseCase(권한 위임, 문서 목록 조회)

**수정 파일**:
1. `src/infrastructure/doc_browse/models.py` — Column 추가 + Index
2. `src/api/routes/knowledge_base_router.py` — `GET /{kb_id}/documents` 엔드포인트
3. `src/api/main.py` — `ListKbDocumentsUseCase` DI 팩토리
4. `src/application/unified_upload/use_case.py` — `kb_id=request.extra_metadata.get("kb_id")` (1줄)

**테스트** (신규 12):
- `tests/application/knowledge_base/test_list_documents_use_case.py`: 6건 (정상/권한/미존재/필터/페이지/빈 목록)
- `tests/application/unified_upload/…`: 2건 (kb_id 저장/미저장)
- `tests/infrastructure/doc_browse/…`: 4건 (쿼리 구성)

**회귀**: 506건 통과 (53건 Windows 이벤트루프 교차실행 이슈, 격리 실행 확인)

### 프론트엔드 (idt_front/)

**신규 페이지**:
1. `src/pages/KnowledgeBasesPage/index.tsx` — KB 목록 (생성/삭제 모달 상태 소유)
2. `src/pages/KnowledgeBaseDetailPage/index.tsx` — KB 상세 (문서 목록 + 업로드)

**신규 컴포넌트** (`src/components/knowledge-base/`):
1. `KnowledgeBaseTable.tsx` — 목록 테이블 (이름/scope/설명/컬렉션/생성일/삭제)
2. `CreateKnowledgeBaseModal.tsx` — 생성 폼 (이름/설명/scope/부서/컬렉션/고급)
3. `DeleteKnowledgeBaseDialog.tsx` — 삭제 확인
4. `KbDocumentTable.tsx` — 문서 목록 테이블
5. `KbUploadDocumentModal.tsx` — 파일 업로드 + 결과

**타입/서비스/훅 확장**:
1. `types/ragToolConfig.ts` (확장) — `KnowledgeBaseInfo` optional 필드
2. `types/knowledgeBase.ts` (신규) — Request/Response 타입
3. `constants/api.ts` (확장) — KB 엔드포인트 상수
4. `services/knowledgeBaseService.ts` (확장) — 6개 메서드
5. `lib/queryKeys.ts` (확장) — detail/documents 키
6. `hooks/useKnowledgeBases.ts` (확장) — 6개 훅 + mutation invalidate

**라우팅/사이드바**:
1. `App.tsx` (수정) — `/knowledge-bases` + `/knowledge-bases/:kbId` 라우트
2. `AppSidebar.tsx` (수정) — '지식베이스' 항목 + `startsWith` active
3. `__tests__/mocks/handlers.ts` (확장) — KB MSW 핸들러

**테스트** (신규 15):
- `pages/KnowledgeBasesPage/index.test.tsx`: 6건
- `components/knowledge-base/CreateKnowledgeBaseModal.test.tsx`: 3건
- `pages/KnowledgeBaseDetailPage/index.test.tsx`: 6건
- 회귀: 20건 + tsc 0 에러

---

## 검증 결과

### 매치율 진행

| 단계 | 판정 | 사항 |
|------|------|------|
| 최초 Check | **93.8%** (30/32) | scope 라벨, DetailPage ⑫⑬, repo kb_id 업데이트 |
| Check 내 해소 | 3건 → +3% | 설계 정정, 테스트 2건 추가, 코드 1줄 |
| **최종** | **96.9%** (31/32) | Act 불필요 |

### 테스트 통과율

**백엔드**:
- 신규: 12/12 (100%)
- 회귀: 506/506 + 53건 기지 이슈 (격리 실행 전건 통과)

**프론트**:
- 신규: 15/15 (100%)
- 회귀: 20/20 + tsc 0 에러 (100%)

### 잔여 Gap

| Gap | 심각도 | 대응 |
|-----|:------:|------|
| **G3** | Low (기지) | E2E 수동 검증 (KB 생성→업로드→agent-builder 드롭다운→검색 격리). **kb-rag-filter G2와 묶어 일괄 실측 예정** (백엔드+Qdrant/ES 기동 필요) |

---

## 남은 항목 & 후속 PDCA

### 배포 전 필수

- ✅ V047 DB 마이그레이션 적용

### 알려진 한계 (명기됨)

- **D4**: KB 생성 이전의 업로드 문서(`kb_id=NULL`)는 목록에 미표시 — knowledge-base-scoping E2E 미수행 상태라 실데이터 사실상 없음
- **FR-05**: 섹션요약 진행률 폴링 없음 — "요약 생성 중" 뱃지만 표시

### 후속 기능 (Backlog)

| # | Feature | 설명 | 선행 |
|---|---------|------|------|
| 1 | `kb-rename` | KB 이름/설명 수정 (PATCH API + UI) | kb-management-ui ✅ |
| 2 | `kb-document-management` | KB 내 문서 삭제·청크 보기 | kb-management-ui ✅ |
| 3 | `section-summary-status-ui` | 요약 진행률 폴링 + 재시도 | kb-management-ui ✅ |
| 4 | `collection-picker-retirement` | agent-builder 컬렉션 드롭다운 은퇴 | kb-management-ui ✅ |
| 5 | `kb-orphan-cleanup` | soft-delete KB 벡터 정리 | kb-management-ui ✅ |

---

## Lessons Learned

### What Went Well

1. **Plan 단계 조사의 가치** — "컬렉션 문서 목록 재사용 시 타 KB 문서 노출" 함정을 조사에서 발견해 최소 백엔드 1건으로 범위 확정. 신규 API 설계가 D1(MySQL 직접 조회) 선택으로 귀결됨.

2. **선례 복제 전략** — CollectionPage/CollectionDocumentsPage 선례를 그대로 복제(페이지 모달 상태 소유, 공용 컴포넌트, react-query 패턴)해 프론트 편차 최소화. 신규 15개 테스트 전건 통과, 회귀 20개 무회귀.

3. **코드 = 진실 소스 원칙** — Check 내 scope 배지 불일치 발견 시 설계 문서를 정정(기존 `SCOPE_LABELS` 재사용)하고 dead code 제거. "설계→코드" 일방향이 아닌 양방향 검증으로 정확성 확보.

4. **TDD 규율** — 백엔드 6+6 테스트(UseCase 정상·권한·미존재·필터·페이지·빈 목록 + 업로드 kb_id), 프론트 15개(목록 6 + 모달 3 + 상세 6) 모두 사전 작성 → 구현 중 설계 이탈 조기 적발.

### Areas for Improvement

1. **E2E 검증 시기** — G3 수동 검증(KB 생성→업로드→검색 격리)이 implementation 직후 실행되지 못함. 차후 기능은 unit test 완료 직후 즉시 E2E 스크립트 작성(kb-rag-filter 학습).

2. **repo update 경로 방어** — kb_id 저장 시 update 경로(`existing.kb_id`) 누락(비즉 재현 아니라 보강 기록). 향후 db mutation 발생 시 직접 쿼리+업데이트 경로 모두 체크.

3. **Windows 테스트 환경 문서화** — 이번 사이클에서도 pytest 교차실행 시 53건 간헐 실패(기지 이슈, 격리 실행 통과). 프로젝트 CI/CD 문서에 `pytest -v tests/` (추천 격리) vs `pytest tests/` (교차 실행) 트레이드오프 명기 필요.

### To Apply Next Time

1. **Plan 조사 체크리스트**: 기존 API/스키마 재사용 가능성(이번: document_metadata 조회), 권한 위임 가능성(이번: can_read), 에러 계약 상속 가능성 → 범위 확정 전 3가지 확인.

2. **설계 문서 정정 기준**: 코드 구현 중 설계 오류 발견 시 (a) 비즈니스 영향 있으면 설계 정정, (b) 표기법/라벨 오류면 문서만 정정, (c) 비본질 오류면 record로 기록 → 이번 scope 배지는 (b)로 설계 정정 실행.

3. **mutation invalidate 일관성**: 생성/삭제 후 `.all` invalidate(이번: `queryKeys.knowledgeBases.all`)로 관련 쿼리 자동 갱신 → agent-builder 드롭다운 동기화 자동 해결. 향후 cross-domain mutation은 모두 `.all` 전략 적용.

---

## 버전 정보

| 항목 | 값 |
|------|-----|
| Backend Version | 커밋 `1466ef9b` (skills 추가 시점) |
| Frontend Version | 커밋 `1466ef9b` 동일 |
| DB Migration | **V047** (필수 적용) |

---

## 승인 체크리스트

- [x] 설계-구현 매치율 96.9% (31/32) ≥ 90%
- [x] 테스트 전건 통과 (BE 신규 12 + FE 신규 15 + 회귀 526)
- [x] tsc 신규 에러 0
- [x] 기존 기능 회귀 0 (회귀 테스트 그린)
- [x] PDCA 일관성 검증 완료
- [ ] E2E 수동 검증 (G3, 후속 kb-rag-filter G2와 묶어 일괄 실측)
- [x] V047 배포 준비 완료

---

## 참고문서

- **Plan**: `docs/01-plan/features/kb-management-ui.plan.md`
- **Design**: `docs/02-design/features/kb-management-ui.design.md`
- **Analysis**: `docs/03-analysis/kb-management-ui.analysis.md`
