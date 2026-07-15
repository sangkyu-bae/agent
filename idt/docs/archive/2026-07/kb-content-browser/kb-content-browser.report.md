# kb-content-browser Completion Report

> **Date**: 2026-07-14  
> **Feature**: KB 상세에서 저장된 3계층 데이터(문서 요약 → 섹션 요약 → 청크)를 드릴다운으로 확인하는 화면  
> **Status**: ✅ Completed  
> **Match Rate**: 97.4%  
> **Iterations**: 0

---

## Executive Summary

### 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **Feature** | KB 콘텐츠 브라우저 — 저장된 3계층 데이터(청크·섹션 요약·문서 요약) 드릴다운 뷰어 |
| **기간** | 2026-07-14 (단일 세션 Plan→Design→Do→Check) |
| **Owner** | 백상규 |
| **Plan** | docs/01-plan/features/kb-content-browser.plan.md |
| **Design** | docs/02-design/features/kb-content-browser.design.md |
| **Analysis** | docs/03-analysis/kb-content-browser.analysis.md |

### 결과 요약

| 구분 | 값 |
|------|-----|
| **Match Rate** | 97.4% (Match 37 + Partial 2 = 38.0 / 39항목) |
| **Iteration** | 0회 (≥90% 도달, Act 불필요) |
| **백엔드 신규 파일** | 7개 (UseCase 3종 + Guard + 헬퍼 + 스키마) |
| **백엔드 수정 파일** | 3개 (라우터 + 메인 DI + GetChunksUseCase 리팩토링) |
| **프론트 신규** | 4컴포넌트 + 4테스트 |
| **프론트 수정** | 6파일 (타입·서비스·훅·테이블·페이지) |
| **테스트 통과** | 백엔드 69건 + 프론트 23건 (신규+회귀) |
| **TypeScript** | tsc --noEmit 무오류 |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | KB에 저장된 3계층 데이터(청크·섹션 요약·문서 요약)를 확인할 API/화면이 없었고, ES와 Qdrant 이중 저장의 정합성을 검증할 수 없었다. 요약 본문은 조회 API 자체가 없었다. |
| **Solution** | KB 라우터 하위 조회 API 3종 신규(문서요약/섹션요약목록/청크조회), 모든 API에 source 토글(ES\|Qdrant) 파라미터 추가. KB 상세 패널에서 저장소별로 3계층을 드릴다운으로 확인 가능하게 구현. |
| **Function/UX Effect** | 업로드→청킹→요약 생성 결과를 눈으로 검증 가능(요약 진행률/재시도 포함). 청크 키워드 검색, Qdrant payload 메타 표시로 저장 정합성 디버깅 도구 역할. 요약 미생성 문서는 `exists:false` 안내로 상태 구분 가능. |
| **Core Value** | ES 우선-Qdrant 마지막 이중 쓰기 구조의 저장 정합성을 한 화면에서 교차 검증할 수 있어, 검색 품질 이슈의 원인이 저장 단계인지 검색 단계인지 즉시 구분 가능. |

---

## 2. PDCA 사이클 요약

### Plan (2026-07-14)
- **문서**: docs/01-plan/features/kb-content-browser.plan.md
- **목표**: KB 상세 화면에서 3계층 데이터 드릴다운 뷰어 추가 (API 3종 신규 + 프론트 패널)
- **핵심 결정**:
  - 백엔드: KB 스코프 조회 API 3종 신규(컬렉션 API는 무변경)
  - 기존 인프라 활용: `GetChunksUseCase` 패턴, `KnowledgeBaseUseCase` 권한 검증 재사용
  - 청크 키워드 검색/요약 조회 소스는 Design에서 결정 예정

### Design (2026-07-14)
- **문서**: docs/02-design/features/kb-content-browser.design.md
- **결정사항 9개 (D1~D9)**:
  - **D1**: KB 라우터 하위 독립 신규 (doc_browse_router 무변경 opt-in)
  - **D2**: 모든 API에 `source: qdrant | es` 파라미터 (사용자 저장소 토글 선택)
  - **D3**: 청크 검색 ES=match(nori) / Qdrant=contains, search_mode 응답으로 UI 차이 표기
  - **D4**: KB 소속 검증 공통 가드 (404/403 + kb_id 일치)
  - **D5**: summary_text 정규화 + payload를 metadata dict로 원본 노출
  - **D6**: 요약 미생성 시 `{exists: false}` (404 아님)
  - **D7**: Qdrant scroll 직접 사용, chunk_type 필터로 계층 분리
  - **D8**: 서버 페이지네이션 없이 전량(10000), 프론트 클라이언트 페이징
  - **D9**: 섹션요약 잡 상태 폴링(running 시 5초) + 재시도 mutation
- **주요 기술 결정**:
  - chunk_assembler.py로 계층/전략 처리 추출 → GetChunksUseCase는 헬퍼 위임(무변경 보증)
  - ES/Qdrant 필드 다중 키 폴백 (summary_text/content)

### Do (2026-07-14)
- **백엔드 (7파일 신규 + 3파일 수정)**:
  - `src/application/knowledge_base/content_browse_guard.py` — KB 소속 검증 공통 가드
  - `src/application/knowledge_base/get_kb_document_summary_use_case.py` — 문서 요약 조회
  - `src/application/knowledge_base/list_kb_section_summaries_use_case.py` — 섹션 요약 목록
  - `src/application/knowledge_base/get_kb_document_chunks_use_case.py` — 청크 조회(kb_id 검증)
  - `src/application/doc_browse/chunk_assembler.py` — 계층/전략 처리 공용 헬퍼 (GetChunksUseCase와 공유)
  - `src/application/doc_browse/browse_sources.py` — Qdrant/ES 소스 분기 로직 (3 UseCase 공유)
  - `src/domain/knowledge_base/browse_schemas.py` — 응답 dataclass (KbDocumentContext 등)
  - `src/api/routes/knowledge_base_router.py` 수정 — 3 엔드포인트 추가 (위임만, 비즈니스 로직 없음)
  - `src/main.py` 수정 — DI 팩토리 3종 + `app.dependency_overrides` 바인딩
  - `src/application/doc_browse/get_chunks_use_case.py` 수정 — chunk_assembler 위임으로 리팩토링 (시그니처/응답 무변경)

- **프론트 (4컴포넌트 신규 + 6파일 수정)**:
  - `src/components/knowledge-base/KbDocumentContentPanel.tsx` — 저장소 토글 + 3탭 컨테이너
  - `src/components/knowledge-base/KbChunkList.tsx` — 청크 계층 + 검색 입력 + 페이지네이션
  - `src/components/knowledge-base/KbSectionSummaryList.tsx` — 섹션 요약 목록 + 잡 진행률/재시도
  - `src/components/knowledge-base/KbPayloadMeta.tsx` — payload 메타 토글 독립 컴포넌트
  - `src/types/knowledgeBase.ts` 수정 — 응답 타입 5종 추가
  - `src/constants/api.ts` 수정 — 엔드포인트 상수 5종
  - `src/services/knowledgeBaseService.ts` 수정 — 서비스 메서드 5종
  - `src/hooks/useKnowledgeBases.ts` 수정 — 훅 5종 + 폴링 로직(D9)
  - `src/lib/queryKeys.ts` 수정 — queryKey 4종
  - `src/components/knowledge-base/KbDocumentTable.tsx` 수정 — 행 클릭/선택 하이라이트
  - `src/pages/KnowledgeBaseDetailPage/index.tsx` 수정 — selectedDoc 상태 + 패널 연결 + 재클릭 닫기

- **테스트 (신규 TDD)**:
  - 백엔드: `test_chunk_assembler.py`, `test_kb_document_guard.py`, `test_get_kb_document_summary_use_case.py`, `test_list_kb_section_summaries_use_case.py`, `test_get_kb_document_chunks_use_case.py`, `tests/api/test_knowledge_base_browse_router.py`
  - 프론트: `KbChunkList.test.tsx`, `KbSectionSummaryList.test.tsx`, `KbDocumentContentPanel.test.tsx`, `KbDocumentTable.test.tsx`
  - MSW 핸들러: 신규 엔드포인트 5종 + 기존 잡 상태 API

### Check (2026-07-14)
- **Match Rate**: 97.4% (Match 37 + Partial 2 / 39항목)
- **결과**:
  - D1~D9 모든 결정사항 구현 완료 (100% Match)
  - 백엔드 설계 10항목 중 9 Match + 1 Partial (B3: 타입 표현 상이만 기능 동등)
  - 프론트 설계 10항목 중 9 Match + 1 Partial (C1: KB 타입을 로컬 신규로 분리 — 계약 동일)
  - 테스트 모두 구현 (Match)
  - Gap Partial 2건: 기능 동등, 영향 낮음
  - Deferred 1건: E2E 브라우저 실측(Qdrant/ES 미기동) → `kb-pipeline-e2e-pending` ⑤로 이월
- **무변경 검증**:
  - `GetChunksUseCase` 공개 시그니처/응답 보존 (내부만 chunk_assembler 위임)
  - `doc_browse_router` 기존 엔드포인트 무변경
  - 요약 파이프라인(DualStoreSummaryWriter, document_summary_step) 읽기만 추가
  - Qdrant/ES 스키마·인덱스 무변경 (payload index 생성 안 함)

---

## 3. 구현 상세

### 3.1 백엔드 아키텍처

**새 모듈 구조**:
```
src/application/knowledge_base/
├── content_browse_guard.py          # 공통 가드: KB 존재 + 문서 소속 검증
├── get_kb_document_summary_use_case.py
├── list_kb_section_summaries_use_case.py
└── get_kb_document_chunks_use_case.py

src/application/doc_browse/
├── chunk_assembler.py               # 신규: 계층/전략 처리 공용 헬퍼
├── browse_sources.py                # 신규: Qdrant/ES 소스별 조회 로직
└── get_chunks_use_case.py           # 수정: chunk_assembler 위임(무변경 계약)

src/domain/knowledge_base/
└── browse_schemas.py                # 신규: KbDocumentContext, 응답 dataclass

src/api/routes/
└── knowledge_base_router.py         # 수정: GET 3종 엔드포인트 추가
```

**API 계약**:
- `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/summary?source=qdrant|es`  
  → `KbDocumentSummaryResponse` {exists, summary_text, keywords, metadata}
- `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summaries?source=qdrant|es`  
  → `KbSectionSummaryListResponse` {items: [section_ref, clause_title, summary_text, chunk_index, metadata]}
- `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/chunks?source=qdrant|es&q=?&include_parent=bool`  
  → `KbDocumentChunksResponse` {chunks, parents, search_mode, total_chunks}

**핵심 설계**:
- 모든 API에 KB 소속 검증 (document_metadata.kb_id 일치 확인)
- 요약 미생성 시 404 대신 `{exists: false}` 응답
- Qdrant: scroll(payload 필터) / ES: bool query(term 필터)
- 청크 검색: ES=match(형태소) / Qdrant=contains(대소문자 무시 부분일치)
- 모든 응답에 `source` 필드 + `metadata` dict로 원본 payload/fields 노출

### 3.2 프론트엔드 아키텍처

**컴포넌트 계층**:
```
pages/KnowledgeBaseDetailPage
├── state: selectedDoc (KbDocumentInfo | null)
├── KbDocumentTable (수정: onRowClick 콜백)
└── {selectedDoc && <KbDocumentContentPanel> (신규 컨테이너)
    ├── 저장소 토글 (Qdrant ↔ Elasticsearch)
    ├── [문서 요약] 탭
    │   └── exists=false 시 "요약 미생성" 안내
    ├── [섹션 요약] 탭
    │   └── <KbSectionSummaryList/>
    │       ├── 잡 상태 폴링(running 5초, 완료 중단)
    │       └── 진행률 바 + 재시도 버튼
    └── [청크] 탭
        └── <KbChunkList/>
            ├── 검색 입력(debounce 400ms)
            ├── parent-child 계층/접기펼치기
            └── search_mode 배지(contains/match)
```

**상태 관리**:
- `useKbDocumentSummary(kbId, docId, source)` → summary_text, keywords
- `useKbSectionSummaries(kbId, docId, source)` → items list
- `useKbDocumentChunks(kbId, docId, {source, q, include_parent})` → chunks + parents
- `useSectionSummaryStatus(kbId, docId)` → job_id, status, done/total(refetchInterval)
- `useRetrySectionSummary(kbId, docId)` mutation

**UI 특이사항**:
- 저장소 토글은 패널 레벨(3탭 공유)
- 검색 q는 선택 저장소에서만 실행(search_mode로 차이 표기)
- Qdrant payload는 모두 str(list는 repr) — 메타 눈검증용 원본 노출
- 페이지네이션 클라이언트측(CARDS_PER_PAGE=6)

### 3.3 API 계약 동기화

✅ **완료**: `/api-contract` 스킬 실행으로 백엔드↔프론트 타입/상수 검증 통과.

---

## 4. 품질 검증

### 4.1 테스트 결과

**백엔드 (pytest 세션 완료)**:
- `test_chunk_assembler.py`: 계층 구성 + 전략 감지 + 동등성(기존 GetChunksUseCase와 일치)
- `test_kb_document_guard.py`: KB 존재검증 + 문서 소속검증(404/403)
- `test_get_kb_document_summary_use_case.py`: 소스별(qdrant/es) 조회 + exists=false
- `test_list_kb_section_summaries_use_case.py`: 섹션 목록 정렬(chunk_index 숫자) + 페이징
- `test_get_kb_document_chunks_use_case.py`: 요약 제외 + q 검색(contains/match) + include_parent + search_mode
- `tests/api/test_knowledge_base_browse_router.py`: 3 엔드포인트 200/404/403 + source 검증(422)

**결과**: 신규 + 회귀 69건 모두 통과  
(WinError 10014 환경 간헐 이슈는 지정 재실행으로 전건 확인)

**프론트 (Vitest --pool=threads)**:
- `KbChunkList.test.tsx`: parent-child 계층 + 접기펼치기 + 검색 입력 + search_mode + 메타 토글 + 페이징
- `KbSectionSummaryList.test.tsx`: 목록 렌더 + running 진행률 + 재시도 mutation + completed 상태
- `KbDocumentContentPanel.test.tsx`: 탭 전환 + 저장소 토글(source 변경) + 닫기 + 로딩/에러
- `KbDocumentTable.test.tsx`: 행 클릭 + 선택 하이라이트 (기존 테스트 확장)
- MSW 핸들러: 5 엔드포인트 + 기존 API (각 테스트 파일에 server.listen 3종 훅)

**결과**: 신규 20건 + 기존 KB 3건 모두 통과  
`tsc --noEmit` 무오류

### 4.2 Gap 분석

| Category | 결과 | 근거 |
|----------|------|------|
| **D1~D9** | ✅ 100% Match | 9/9 결정사항 구현 완료 |
| **백엔드 설계** | ✅ 95% (9/10) | B3 Partial: 정규식 vs Literal(기능 동등), 응답 스키마 일치 |
| **프론트 설계** | ✅ 95% (9/10) | C1 Partial: KB 로컬 타입 신규(collection과 chunk_type 계약 미세 차이) |
| **테스트** | ✅ 100% Match | 6 backend + 4 frontend 전부 존재, MSW 핸들러 5종 |
| **수용 기준** | ✅ 100% (8/8) | 1 Deferred(E2E 브라우저 실측) — Missing 아님 |

**Partial 분석**:
- **P1 (B3)**: `Query(pattern="^(qdrant\|es)$")` vs 설계 `Literal`. 422 동일 → 설계 문서 갱신 권장 (Code is truth)
- **P2 (C1)**: KB 응답이 collection 타입과 `chunk_type`, `metadata` 필드 계약이 다름(string vs typed) → 의도적 로컬 분리 타당

**Deferred 분석**:
- **DF1**: 저장소 토글 브라우저 실측(ES/Qdrant 동시 기동 필요) → `kb-pipeline-e2e-pending` 체크리스트 ⑤로 이월 (Missing 아님, 테스트로 검증됨)

### 4.3 추가 구현 평가

| 항목 | 설계 vs 구현 | 평가 |
|------|-------------|------|
| A1: `KbPayloadMeta.tsx` | 신규(설계는 inline) | ✅ 재사용 컴포넌트로 승격 — 코드 품질 향상 |
| A2: `browse_sources.py` | 신규(설계는 UseCase private) | ✅ 3 UseCase DRY 강화 |
| A3: `KbDocumentContext.chunk_strategy` | 추가 필드 | ✅ filename 폴백 활용 — 견고성 |
| A4: 요약 다중 키 폴백 | ES/Qdrant 필드 차이 흡수 | ✅ 동적 필드 매핑(summary_text/summary/content) |

---

## 5. 남은 작업 / 후속

### 5.1 직후속 (V048에 예정)

1. **Design 문서 갱신**  
   - `kb-content-browser.design.md` §4.3 소스 검증 방식 `Literal` → `pattern` 반영  
   - P2 로컬 타입 분리 의도 기록 (또는 후속 통합 고려)

2. **E2E 브라우저 실측**  
   - Qdrant + Elasticsearch 기동 환경에서 저장소 토글 동작 확인  
   - `kb-pipeline-e2e-pending` 체크리스트 ⑤: kb-content-browser  
   - V047(kb_id 추가) 적용 선행 필수

### 5.2 확장 후보 (미래)

| 기능 | 설명 | Out-of-Scope 근거 |
|------|------|------------------|
| **KB 전체 횡단 검색** | 문서 지정 없이 KB 내 모든 청크 검색 | Plan Out-of-Scope, 별도 설계 필요 |
| **Qdrant 풀텍스트 인덱스** | `create_payload_index(MatchText)` 추가 | Design D3에서 명시 제외(마이그레이션 영향), 향후 검토 |
| **청크 편집/재생성** | 조회 후 요약 본문 수정, 재생성 트리거 | Plan Out-of-Scope |
| **임베딩 벡터 시각화** | vector 값 표시 | Plan Out-of-Scope(메타 눈검증만) |
| **ES/Qdrant 정합성 자동 진단** | 두 저장소 결과 diff 시각화 | Plan Out-of-Scope(눈검증 도구로 충분) |

---

## 6. Lessons Learned

### 6.1 What Went Well ✅

1. **공용 헬퍼 추출 (chunk_assembler.py)**  
   - 기존 `GetChunksUseCase`의 계층/전략 처리를 공용 헬퍼로 추출해 3 UseCase(GetChunks + 신규 2)가 공유  
   - DRY 원칙으로 요약/청크 계층 처리의 동등성 보증  
   - GetChunksUseCase 공개 계약 보존 (내부만 리팩토링)

2. **ES/Qdrant 이중 저장 수용**  
   - Design에서 "한쪽을 고르지 말고 둘 다 보기" 결정 (D2)  
   - source 토글로 사용자가 저장소별 정합성 교차 검증 가능  
   - 두 저장소의 필드 차이(summary_text vs content)를 다중 키 폴백으로 자동 흡수

3. **요약 미생성 상태 명확화**  
   - 404 대신 `{exists: false}` 응답으로 "조회 권한 없음" vs "미생성 문서" 구분  
   - 사용자 입장에서 상태 불명확성 제거

4. **API 계약 동기화 완전성**  
   - 백엔드 응답 스키마 ↔ 프론트 타입/서비스/훅 일관성 검증 완료  
   - `/api-contract` 스킬로 자동 검증 (계약 이탈 조기 발견)

### 6.2 Areas for Improvement 🔧

1. **Qdrant 풀텍스트 인덱스 부재**  
   - Qdrant는 `payload_index(MatchText)` 없어 키워드 검색이 scroll 후 Python 부분일치만 가능  
   - ES는 nori 형태소 분석으로 정밀, Qdrant는 대소문자 무시 포함만  
   - UI에 search_mode 배지로 차이 명시했으나, 향후 마이그레이션으로 인덱스 추가 고려 가치

2. **ES/Qdrant 필드명 일관성**  
   - 섹션요약 ES:`summary_text` vs Qdrant:`content` (그 외 필드도 차이 있음)  
   - 응답 정규화로 외부에는 감출 수 있으나, 내부 소스별 로직이 복잡  
   - 향후 저장 파이프라인 정합성 개선 시 필드명 통일 추천

3. **V047 이전 레거시 문서**  
   - kb_id NULL인 문서는 KB API에서 404 (의도적, kb-management-ui와 정책 동일)  
   - 그러나 혼란 가능 → 마이그레이션 문서에 명시 필요

### 6.3 To Apply Next Time 💡

1. **chunk_assembler 패턴 재사용**  
   - 여러 UseCase에서 공통 데이터 처리(계층/전략/필터)가 필요한 경우, 공용 헬퍼로 추출하고 테스트로 동등성 보증  
   - 기존 공개 계약은 보존(내부 리팩토링)

2. **source 토글 설계**  
   - ES/Qdrant 같은 이중 저장 구조에서 "하나 선택" 대신 "둘 다 보기" 결정이 유효  
   - 사용자 입장에서 정합성 검증 도구 역할 → 프로덕트 가치 증가

3. **명확한 상태 응답**  
   - "없음(404)" vs "미생성(exists=false)"을 구분하는 것이 UX 명확성을 높임  
   - API 설계 시 상태 스펙트럼(존재 여부 vs 생성 여부)을 먼저 정의

4. **테스트 순서 (TDD)**  
   - 테스트 먼저 작성해 설계와 구현의 갭을 조기 발견  
   - chunk_assembler 동등성 테스트로 GetChunksUseCase 회귀 방지

---

## Appendix: 파일 변경 요약

### 백엔드 (idt/)

**신규 7파일**:
```
src/application/knowledge_base/content_browse_guard.py
src/application/knowledge_base/get_kb_document_summary_use_case.py
src/application/knowledge_base/list_kb_section_summaries_use_case.py
src/application/knowledge_base/get_kb_document_chunks_use_case.py
src/application/doc_browse/chunk_assembler.py
src/application/doc_browse/browse_sources.py
src/domain/knowledge_base/browse_schemas.py
```

**수정 3파일**:
```
src/api/routes/knowledge_base_router.py          (+3 GET 엔드포인트)
src/main.py                                      (+3 DI 팩토리, +3 overrides)
src/application/doc_browse/get_chunks_use_case.py (+chunk_assembler 위임, -내부 로직)
```

**테스트 신규 6파일**:
```
tests/application/knowledge_base/test_kb_document_guard.py
tests/application/knowledge_base/test_get_kb_document_summary_use_case.py
tests/application/knowledge_base/test_list_kb_section_summaries_use_case.py
tests/application/knowledge_base/test_get_kb_document_chunks_use_case.py
tests/application/doc_browse/test_chunk_assembler.py
tests/api/test_knowledge_base_browse_router.py
```

### 프론트엔드 (idt_front/)

**신규 4컴포넌트**:
```
src/components/knowledge-base/KbDocumentContentPanel.tsx
src/components/knowledge-base/KbChunkList.tsx
src/components/knowledge-base/KbSectionSummaryList.tsx
src/components/knowledge-base/KbPayloadMeta.tsx
```

**수정 6파일**:
```
src/types/knowledgeBase.ts
src/constants/api.ts
src/services/knowledgeBaseService.ts
src/hooks/useKnowledgeBases.ts
src/lib/queryKeys.ts
src/components/knowledge-base/KbDocumentTable.tsx
src/pages/KnowledgeBaseDetailPage/index.tsx
```

**테스트 신규 4파일**:
```
src/components/knowledge-base/KbChunkList.test.tsx
src/components/knowledge-base/KbSectionSummaryList.test.tsx
src/components/knowledge-base/KbDocumentContentPanel.test.tsx
src/components/knowledge-base/KbDocumentTable.test.tsx (기존 확장)
```

---

## Summary

✅ **Match Rate 97.4%** — 설계와 구현 정합도 매우 높음.  
✅ **D1~D9 결정사항 100% 반영** — 설계 주요 기술 결정 모두 구현.  
✅ **테스트 완전성** — 백엔드 69건 + 프론트 23건 모두 통과, 회귀 없음.  
✅ **무변경 계약 보증** — GetChunksUseCase·doc_browse_router·요약 파이프라인 공개 계약 보존.  
⏸️ **Deferred 1건** — E2E 브라우저 실측(Qdrant/ES 미기동) → kb-pipeline-e2e-pending ⑤로 이월.

**다음 단계**: 설계 문서 갱신(P1) → Qdrant/ES 기동 환경에서 E2E 검증 → 배포.
