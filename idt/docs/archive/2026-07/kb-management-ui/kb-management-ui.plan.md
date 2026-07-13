# kb-management-ui Plan — 지식베이스 관리 화면

> **Status**: Plan
> **Date**: 2026-07-10
> **선행**: knowledge-base-scoping (백엔드 KB 계층, 아카이브), kb-rag-filter (agent-builder KB 선택 UI, 아카이브)
> **작업 디렉토리**: `idt_front/` 중심 + `idt/` 백엔드 1건

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 백엔드 KB API(CRUD+업로드+섹션요약)는 완비됐고 agent-builder에서 KB를 *선택*할 수는 있지만, KB를 *만들고 문서를 넣는* 화면이 없다. 현재 KB 생성·업로드는 API 직접 호출로만 가능해 일반 사용자는 kb-rag-filter 기능을 실사용할 수 없다. |
| **Solution** | 독립 페이지 `/knowledge-bases` 신설(사이드바 항목 추가): KB 목록·생성·삭제 + KB 상세(문서 목록)·문서 업로드. 백엔드는 kb_id 필터 문서 목록 API 1건만 추가, 나머지는 기존 API 소비. |
| **Function/UX Effect** | 사용자가 지식베이스를 만들고(이름·설명·scope·컬렉션·조항청킹 토글) 문서를 업로드한 뒤, agent-builder에서 그 KB를 골라 검색 범위를 격리하는 전체 흐름이 UI로 완성된다. 업로드 결과(청크 수·저장 상태·요약 잡 킥오프)를 즉시 확인. |
| **Core Value** | "문서 물리 관리(관리자) → 논리 조직화(사용자) → 에이전트 검색 격리" 파이프라인의 사용자 진입점 완성 — 단일 컬렉션 전환 로드맵(컬렉션 드롭다운 은퇴)의 전제 조건. |

---

## 1. 배경 / 문제

- knowledge-base-scoping이 논리 KB 계층(MySQL `knowledge_base` + `/api/v1/knowledge-bases` CRUD + 업로드 시 청크 payload `kb_id` 주입)을 완성.
- kb-rag-filter가 agent-builder에 KB **선택** 드롭다운을 연결 — 그러나 선택할 KB를 **만들 화면이 없음**.
- 프론트 기존 자산: `knowledgeBaseService.getKnowledgeBases()`(목록만), `useKnowledgeBases` 훅, `KnowledgeBaseInfo` 타입(축약형), `API_ENDPOINTS.KNOWLEDGE_BASES`.

## 2. 확정 결정 (사용자 확인, 2026-07-10)

| # | 질문 | 결정 |
|---|------|------|
| Q1 | 화면 범위 | **목록·생성·삭제 + 문서 업로드** (섹션요약 진행률/재시도 UI는 후속) |
| Q2 | 이름/설명 수정(rename) | **이번 범위 제외** (백엔드 PATCH 부재, kb_id 불변이라 후속 추가에 데이터 영향 없음) |
| Q3 | 청킹 옵션 노출 | **use_clause_chunking 토글만** (고급 접기, 프로파일 목록 API가 admin 전용이라 프로파일 선택 노출 불가 → NULL late-binding) |
| Q4 | 위치 | **독립 페이지 `/knowledge-bases`** + 사이드바 항목 (물리 컬렉션 `/collections`과 분리) |

## 3. 기능 요구사항 (FR)

### 프론트엔드 (idt_front/)

- **FR-01 KB 목록 페이지** — `/knowledge-bases` 라우트(`ProtectedRoute` + `AgentChatLayout`), `AppSidebar` '지식베이스' 항목 추가. 카드/테이블에 이름·scope 배지(개인/부서/전체공개)·설명·컬렉션명·생성일 표시. 빈 목록 시 생성 유도 문구.
- **FR-02 KB 생성 폼(모달)** — 이름(필수, ≤100자)·설명·scope(PERSONAL 기본/DEPARTMENT+부서선택/PUBLIC)·대상 컬렉션 선택(기존 `collectionService` 목록 재사용)·고급 접기: `use_clause_chunking` 토글. `POST /api/v1/knowledge-bases`. 에러 표면화: 409(이름 중복)·422(scope/컬렉션 검증)·403.
- **FR-03 KB 삭제** — 소유자/관리자만 버튼 노출(owner_id 비교), 확인 다이얼로그에 soft-delete 안내("저장된 벡터는 정리 작업 전까지 남습니다" — 백엔드 응답 문구 반영). `DELETE /{kb_id}`.
- **FR-04 KB 상세** — 목록에서 진입, `GET /{kb_id}` 정보 + **KB 내 문서 목록**(FR-08 신규 API 소비: 파일명·청크 수·업로드일). 문서 삭제/청크 보기는 비범위.
- **FR-05 문서 업로드** — KB 상세에서 파일 선택 → `POST /{kb_id}/documents`(multipart). 업로드 중 스피너(동기 파싱+임베딩이라 수십 초 가능), 완료 시 결과 표시: chunk_count·chunking_strategy·qdrant/es 상태·section_summary 킥오프 여부(있으면 "요약 생성 중" 뱃지 — 폴링은 후속).
- **FR-06 타입/서비스/훅 확장** — `KnowledgeBaseInfo`를 백엔드 `KbInfoResponse` 전체 필드로 확장(owner_id·use_clause_chunking·created_at 등), `knowledgeBaseService`에 get/create/delete/upload/listDocuments 추가, `queryKeys.knowledgeBases` detail/documents 키 추가, mutation 후 `list()` invalidate.
- **FR-07 기존 동작 보존** — agent-builder `RagConfigPanel` KB 드롭다운은 동일 서비스·queryKey 공유로 무수정 동작(생성/삭제 후 드롭다운 자동 갱신은 staleTime 5분 내 invalidate로 보장). 기존 테스트 무회귀.

### 백엔드 (idt/) — 이번 사이클 유일한 신규 API

- **FR-08 KB 문서 목록 API** — `GET /api/v1/knowledge-bases/{kb_id}/documents`. KB는 물리 컬렉션을 다른 KB와 **공유**하므로 기존 컬렉션 단위 문서 목록(`doc_browse`)을 쓰면 타 KB 문서가 노출됨 → `kb_id` payload 필터로 문서 단위 집계(document_id·filename·chunk_count·업로드 시각). 권한은 기존 `KnowledgeBaseUseCase.get()`의 can_read 검증 재사용(403/404 매핑 `_raise_http` 동일). TDD.

## 4. 비범위 (Out of Scope)

| 항목 | 사유 / 행선지 |
|------|--------------|
| KB 이름/설명 수정 | 백엔드 PATCH 부재 → 후속 `kb-rename` |
| 청킹 프로파일 선택·size/overlap 입력 | 프로파일 목록 admin 전용 → admin 화면 후속 |
| KB 내 문서 삭제·청크 브라우징 | 후속 `kb-document-management` (컬렉션 브라우저는 기존 존재) |
| 섹션요약 진행률 폴링·재시도 UI | 후속 `section-summary-status-ui` (킥오프 뱃지 표시까지만) |
| 컬렉션 드롭다운 은퇴 | 후속 `collection-picker-retirement` |
| soft-delete KB 벡터 정리 | 후속 `kb-orphan-cleanup` |

## 5. 현재 상태 (As-Is 조사, 2026-07-10)

| 영역 | 상태 |
|------|------|
| 백엔드 API | `POST/GET/GET{id}/DELETE /api/v1/knowledge-bases`, `POST /{kb_id}/documents`, 섹션요약 상태/재시도 — 전부 존재. **kb_id 필터 문서 목록만 부재** |
| 프론트 서비스 | `knowledgeBaseService.getKnowledgeBases()`만 존재 (kb-rag-filter 산출물) |
| 라우팅 선례 | `App.tsx` — `/collections`(CollectionPage) + `/collections/:name/documents`(CollectionDocumentsPage)가 목록/상세 구조 선례 |
| 사이드바 | `AppSidebar.tsx` nav 배열 — '리소스'(/collections) 항목 옆에 추가 |
| 업로드 선례 | `unifiedUploadService`(multipart 업로드), CollectionDocumentsPage 업로드 흐름 |
| 부서 선택 | `departmentService` 존재 (DEPARTMENT scope용 부서 목록) |

## 6. 리스크

| # | 리스크 | 대응 |
|---|--------|------|
| R1 | 업로드가 동기 처리(파싱+임베딩) — 대용량 PDF에서 수십 초 지연 | 업로드 중 명시적 스피너+안내, axios timeout 상향(서비스 단위), 실패 시 에러 표면화 |
| R2 | 읽기 가능한 컬렉션이 없는 사용자는 KB 생성 불가(컬렉션 생성은 admin 전용) | 생성 폼 컬렉션 빈 목록 시 "관리자에게 컬렉션 생성을 요청하세요" 안내 |
| R3 | FR-08 집계 성능 — 청크 수가 큰 컬렉션에서 kb_id 필터 집계 비용 | ES `kb_id` keyword 매핑 기존 반영(knowledge-base-scoping) — terms 집계로 처리, 문서 수 상한 페이지네이션 |
| R4 | Windows 테스트 환경 | vitest `--pool=threads`, MSW per-file `server.listen` 3종 훅, 백엔드 pytest 격리 실행 (기지 사항) |
| R5 | KB 생성 직후 agent-builder 드롭다운 미갱신 오인 | 동일 queryKey invalidate로 해결 — 회귀 테스트에 포함 |

## 7. 수용 기준

- [ ] `/knowledge-bases`에서 KB 목록·생성·삭제 동작 (MSW 테스트: 성공 + 409 중복 이름 + 403)
- [ ] KB 상세에서 문서 목록 조회 + 업로드 → 결과(청크 수·저장 상태) 표시 (MSW 테스트)
- [ ] FR-08 백엔드: 권한(403)·미존재(404)·kb_id 격리(타 KB 문서 미노출) pytest
- [ ] agent-builder RagConfigPanel 기존 테스트 무회귀, tsc 신규 에러 0
- [ ] TDD: 테스트 먼저 작성 (백엔드 pytest Red→Green, 프론트 Vitest+RTL+MSW)

## 8. 후속 (Follow-ups)

1. `kb-rename` — PATCH API + 편집 UI
2. `kb-document-management` — KB 내 문서 삭제·청크 보기
3. `section-summary-status-ui` — 요약 잡 진행률 폴링 + 재시도
4. `collection-picker-retirement` — agent-builder 컬렉션 드롭다운 은퇴 (KB 보급 후)
5. `kb-orphan-cleanup` — soft-delete KB 벡터 정리
