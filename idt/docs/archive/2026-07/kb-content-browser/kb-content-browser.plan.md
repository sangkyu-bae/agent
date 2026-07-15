# Plan: kb-content-browser

> Feature: KB 상세에서 저장된 3계층 데이터(문서 요약 → 섹션 요약 → 청크)를 드릴다운으로 확인하는 화면
> Created: 2026-07-14
> Status: Plan
> Priority: High
> Related: `kb-management-ui` (archived 2026-07), `summary-routed-retrieval` (archived), `card-section-summary` (archived), `document-summary-routing` (archived), `collection-document-browser` (완료 — 컬렉션 단위 청크 뷰어)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | KB 단위로 문서를 나눠 저장하기 시작했지만, KB 안에 실제로 무엇이 어떻게 저장됐는지(청크 본문, 섹션 요약, 문서 요약) 확인할 화면이 없다. 요약 본문은 조회 API 자체가 없어 라우팅 검색을 통해서만 간접 확인 가능하다. |
| **Solution** | KB 상세 페이지의 문서 테이블에서 문서를 클릭하면 3계층(문서 요약 → 섹션 요약 → parent/child 청크)을 드릴다운으로 보여주는 뷰어를 추가한다. 백엔드는 KB 스코프 조회 API 3종을 신규로 만든다(기존 컬렉션 API는 건드리지 않음). |
| **Function/UX Effect** | 업로드 → 청킹 → 요약 생성 결과를 눈으로 검증 가능. 요약 잡 진행률/재시도, 청크 키워드 검색, Qdrant payload 메타 표시까지 지원해 저장 정합성 디버깅 도구 역할. |
| **Core Value** | 라우팅 검색(3계층 하강)이 "무엇을 보고 판단하는지"를 그대로 볼 수 있어, 검색 품질 이슈의 원인이 저장 단계인지 검색 단계인지 즉시 구분할 수 있다. |

---

## 1. 목적 (Why)

`kb-management-ui`로 KB 생성/삭제/문서 업로드/문서 목록까지 완성됐으나,
**KB에 저장된 실제 내용물을 확인하는 화면이 없다.**

검색 파이프라인은 문서를 3계층으로 저장한다:

```
문서 요약 (1차 라우팅 계층)          → Qdrant/ES, 조회 API 없음
  └─ 섹션 요약 (2차 라우팅 계층)     → ES + Qdrant(chunk_type=section_summary), 잡 상태만 조회 가능
      └─ parent/child 청크 (본문)   → Qdrant/ES, 컬렉션 단위 조회 API만 존재 (KB 스코프 아님)
```

사용자가 KB 상세 화면에서:
1. 문서를 클릭하면 → 해당 문서의 **문서 요약 / 섹션 요약 / 청크**를 계층별로 볼 수 있어야 하고
2. 요약이 아직 생성 중이거나 실패한 문서는 → **잡 진행률과 재시도 버튼**을 같은 화면에서 볼 수 있어야 한다

---

## 2. 현재 상태 분석 (As-Is)

### 이미 구축된 인프라

| 구분 | 상태 | 파일 |
|------|------|------|
| KB 문서 목록 API | ✅ | `GET /api/v1/knowledge-bases/{kb_id}/documents` |
| 섹션 요약 잡 상태 API | ✅ | `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary` (+ `/retry`) |
| 컬렉션 단위 청크 조회 | ✅ | `GET /api/v1/collections/{name}/documents/{id}/chunks` (`GetChunksUseCase`) — KB 필터 아님 |
| KB 상세 페이지 + 문서 테이블 | ✅ | `idt_front/src/pages/KnowledgeBaseDetailPage/index.tsx`, `components/knowledge-base/KbDocumentTable.tsx` |
| KB 서비스/훅/타입 | ✅ | `services/knowledgeBaseService.ts`, `hooks/useKnowledgeBases.ts`, `types/knowledgeBase.ts` |
| 컬렉션용 청크 뷰어 (참고용 선례) | ✅ | `components/collection/ChunkDetailPanel.tsx` — KB 화면과 미연결 |
| 요약 저장 인프라 | ✅ | `DualStoreSummaryWriter` (ES 우선 + Qdrant upsert, 결정적 uuid5 ID) |

### 누락된 부분

| 구분 | 상태 |
|------|------|
| KB 스코프 청크 조회 API | ❌ 없음 (컬렉션 API는 kb_id 검증 없이 노출됨) |
| 섹션 요약 **본문** 조회 API | ❌ 없음 (잡 상태만 조회 가능) |
| 문서 요약 **본문** 조회 API | ❌ 없음 |
| KbDocumentTable 드릴다운 진입점 | ❌ 행 클릭 동작 없음 |
| 3계층 뷰어 UI | ❌ 없음 |

---

## 3. 기능 범위 (Scope)

### In Scope

**A. 백엔드 — KB 스코프 저장 내용 조회 API 3종 (신규)**

- [ ] `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/summary`
  - 문서 요약 본문 반환 (없으면 404가 아닌 `exists: false` 형태 — 요약 미생성 문서 구분)
- [ ] `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summaries`
  - 섹션 요약 목록(섹션 제목 + 요약 본문 + 섹션 순서), 페이지네이션
- [ ] `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/chunks`
  - parent/child 청크 목록. `include_parent` 계층 옵션, 페이지네이션, `q`(키워드 검색) 파라미터
  - Qdrant payload(`kb_id`, `document_id`, `chunk_type`, `chunk_index` 등) 원본 메타 포함 반환
- [ ] 세 API 모두 **문서가 해당 KB 소속(kb_id 일치)인지 검증** 후 조회 — 불일치 시 404
- [ ] 기존 컬렉션 라우터(`doc_browse_router`)는 **수정하지 않음** (독립 신규, 기존 동작 보존)

**B. 프론트 — KB 상세 드릴다운 뷰어**

- [ ] `KbDocumentTable` 행 클릭 → 문서 저장 내용 패널/모달 진입 (선택 행 하이라이트, 재클릭 닫기)
- [ ] 3계층 탭 또는 아코디언 구성: `문서 요약` / `섹션 요약` / `청크`
- [ ] 청크 탭: chunk_index, chunk_type, content(접기/펼치기), parent-child 계층 표시
- [ ] 청크 키워드 검색 입력 → API `q` 파라미터 연동
- [ ] 각 청크/요약 항목에 payload 메타(kb_id, document_id, chunk_type 등) 표시 (접힘 상태 기본)
- [ ] 요약 잡 상태 연동: 섹션 요약 탭에서 잡이 미완료/실패인 경우 진행률 + 재시도 버튼 표시 (기존 잡 상태 API 재사용)
- [ ] 로딩/에러/빈 상태 처리

**C. API 계약 동기화**

- [ ] `idt_front/src/types/knowledgeBase.ts` 타입 추가, `constants/api.ts` 엔드포인트 상수, `knowledgeBaseService.ts` + `useKnowledgeBases.ts` 훅

### Out of Scope

- 청크/요약 내용 편집·삭제·재생성 (재시도는 기존 잡 API 범위만)
- KB 전체 스코프 횡단 검색(문서 지정 없이 KB 내 전체 청크 검색) — 후속 확장
- 임베딩 벡터 값 자체 표시 (payload 메타만; 벡터는 화면 가치 없음)
- 문서 요약 재생성 트리거 (섹션 요약 잡 재시도만 기존 API로)
- ES/Qdrant 이중 저장 정합성 자동 진단 (눈검증용 메타 표시까지만)

---

## 4. UI 설계 (초안)

```
KnowledgeBaseDetailPage
├── KB 메타 카드 (기존)
├── KbDocumentTable (기존 + 행 클릭 추가)
│   └── 문서 행 클릭
│       └── KbDocumentContentPanel (신규 — 하단 확장 패널)
│           ├── [문서 요약] 탭 — 요약 본문 or "요약 없음"
│           ├── [섹션 요약] 탭 — 섹션별 요약 목록
│           │     └── 잡 미완료 시: 진행률 바 + 재시도 버튼
│           └── [청크] 탭 — 검색 입력 + parent/child 계층 목록
│                 └── 각 항목: content 접기/펼치기 + payload 메타 토글
```

```
┌─────────────────────────────────────────────────────────┐
│ 📄 여신심사기준.pdf — 저장 내용                          │
│ [문서 요약] [섹션 요약 ⏳ 12/20] [청크 (84)]             │
├─────────────────────────────────────────────────────────┤
│ (청크 탭)  🔍 [ 키워드 검색        ]                     │
│  #1 [parent] "제3장 여신심사 일반기준..."          ▼    │
│    ├─ #2 [child] "심사역은 차주의 상환능력..."     ▼    │
│    │     ⓘ payload: kb_id=..., chunk_type=child        │
│    └─ #3 [child] "담보평가는 감정평가법인..."      ▼    │
│  [◀ 1 2 3 ▶]                                            │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 기술 의존성 및 설계 결정 포인트

| 항목 | 내용 |
|------|------|
| 청크 조회 소스 | Qdrant scroll (kb_id + document_id payload 필터). 기존 `GetChunksUseCase` 패턴 재사용하되 KB 검증 레이어 추가 |
| 섹션 요약 조회 소스 | **Design에서 결정**: ES(요약 전용 필드) vs Qdrant(chunk_type=section_summary). ES가 원본 저장소이므로 ES 우선 검토 |
| 문서 요약 조회 소스 | `document_summary_step` 저장 위치 확인 후 동일 기준 적용 |
| 청크 키워드 검색 | **Design에서 결정**: Qdrant MatchText(풀텍스트 인덱스 필요 여부 확인) vs ES match query. 인덱스 추가가 필요하면 마이그레이션 영향 검토 |
| KB 소속 검증 | `document_metadata.kb_id` (V047) 기준 — kb_id NULL 문서는 KB API에서 404 |
| 아키텍처 | UseCase 신규 3종 (`application/knowledge_base/` 또는 기존 doc_browse 패턴 준수), router는 위임만 |

---

## 6. 파일 구조 (예상)

### 백엔드 (idt/)

```
src/
├── api/routes/knowledge_base_router.py        # 엔드포인트 3종 추가 (위임만)
├── application/knowledge_base/
│   ├── get_kb_document_summary_use_case.py    # 신규
│   ├── list_kb_section_summaries_use_case.py  # 신규
│   └── get_kb_document_chunks_use_case.py     # 신규 (KB 소속 검증 + 청크 조회)
├── interfaces/schemas/ (또는 기존 스키마 위치) # 응답 스키마 3종
└── infrastructure/                            # 요약 리더(ES/Qdrant) 필요 시 추가
```

### 프론트 (idt_front/)

```
src/
├── components/knowledge-base/
│   ├── KbDocumentContentPanel.tsx   # 신규 — 3계층 탭 컨테이너
│   ├── KbChunkList.tsx              # 신규 — 청크 계층 + 검색
│   └── KbSectionSummaryList.tsx     # 신규 — 섹션 요약 + 잡 상태/재시도
├── components/knowledge-base/KbDocumentTable.tsx  # 수정 — 행 클릭
├── pages/KnowledgeBaseDetailPage/index.tsx        # 수정 — 선택 상태 + 패널 연결
├── services/knowledgeBaseService.ts               # 수정 — API 3종
├── hooks/useKnowledgeBases.ts                     # 수정 — 훅 3종
├── types/knowledgeBase.ts                         # 수정 — 응답 타입
└── constants/api.ts                               # 수정 — 엔드포인트 상수
```

---

## 7. TDD 계획

### 백엔드 (pytest 먼저 작성)

| 테스트 | 대상 |
|--------|------|
| UseCase 단위 테스트 3종 | KB 소속 검증(불일치 404), 요약 없음 시 `exists: false`, 페이지네이션, 키워드 검색 |
| 라우터 테스트 | 응답 스키마, 404 케이스 |

### 프론트 (Vitest + MSW, `--pool=threads`)

| 테스트 | 대상 |
|--------|------|
| `KbDocumentContentPanel.test.tsx` | 탭 전환, 로딩/에러/빈 상태 |
| `KbChunkList.test.tsx` | parent-child 계층, 접기/펼치기, 검색 입력 → 쿼리 반영, payload 메타 토글 |
| `KbSectionSummaryList.test.tsx` | 요약 목록 렌더링, 잡 미완료 시 진행률+재시도 버튼 |
| MSW 핸들러 | 신규 엔드포인트 3종 mock (각 테스트 파일에 server.listen 3종 훅 직접 선언) |

---

## 8. CLAUDE.md 규칙 체크

- [ ] router에 비즈니스 로직 없음 (UseCase 위임)
- [ ] domain → infrastructure 참조 없음
- [ ] TDD: 테스트 먼저 작성
- [ ] 기존 컬렉션 API·요약 파이프라인 무변경 (독립 신규 opt-in)
- [ ] API 계약 동기화 (`/api-cotract` 스킬 실행)

---

## 9. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 문서 요약 저장 위치/스키마가 조회에 부적합할 수 있음 | 중 | Design 단계에서 `document_summary_step` 저장 구조 실사 후 조회 경로 확정 |
| 청크 키워드 검색용 Qdrant 풀텍스트 인덱스 부재 | 중 | ES match query로 대체하거나, MVP는 페이지 내 클라이언트 필터로 축소 가능 (Design에서 확정) |
| kb_id NULL인 레거시 문서는 화면에 안 보임 | 낮 | 기존 `kb-management-ui` 정책과 동일 — KB 업로드 문서만 대상임을 명시 |
| ES/Qdrant 요약 이중 저장 불일치 시 화면 혼동 | 낮 | 조회 소스를 한 곳으로 고정하고 응답에 source 필드 명시 |
| E2E 실측 미수행 상태 (Qdrant/ES 기동 필요) | 중 | `kb-pipeline-e2e-pending` 체크리스트에 본 기능 확인 항목 추가, V047 적용 선행 |

---

## 10. 완료 기준

- [ ] KB 문서 행 클릭 시 저장 내용 패널 표시 (재클릭 닫기)
- [ ] 문서 요약 본문 표시 (미생성 시 안내)
- [ ] 섹션 요약 목록 표시 + 잡 미완료 시 진행률/재시도
- [ ] 청크 parent/child 계층 + content 접기/펼치기 표시
- [ ] 청크 키워드 검색 동작
- [ ] payload 메타(kb_id, document_id, chunk_type) 확인 가능
- [ ] 타 KB 문서 ID로 접근 시 404 (KB 격리 검증)
- [ ] 백엔드/프론트 신규 테스트 전부 통과 (사전 실패 목록과 구분)

---

## 11. 구현 순서 (예상)

| 순서 | 작업 | 예상 |
|------|------|------|
| 1 | 요약 저장 구조 실사 (ES/Qdrant) → 조회 소스 확정 | 30분 |
| 2 | 백엔드 UseCase 3종 + 테스트 (TDD) | 2시간 |
| 3 | 라우터 + 스키마 + 테스트 | 45분 |
| 4 | 프론트 타입/서비스/훅 + MSW 핸들러 | 45분 |
| 5 | `KbChunkList` / `KbSectionSummaryList` / `KbDocumentContentPanel` + 테스트 | 2시간 |
| 6 | `KbDocumentTable` 행 클릭 + 페이지 통합 | 30분 |
| 7 | 브라우저 확인 (백엔드+프론트 dev 서버) | 30분 |

**총 예상: ~7시간 (풀스택)**

---

## 12. 다음 단계

1. [ ] Design 문서 작성 (`/pdca design kb-content-browser`) — 조회 소스·검색 방식 결정 포함
2. [ ] 구현 시작 (TDD)
3. [ ] Qdrant/ES 기동 시 E2E 체크리스트에 편입
