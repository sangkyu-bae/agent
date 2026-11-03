# kb-document-management Analysis Report

> **분석 유형**: Gap 분석 (정적 + 런타임)
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 브랜치 `feature/kb-document-management` (기준 1baf6d1, 미커밋)
> **Analyst**: 배상규 + Claude (정적 분석: gap-detector)
> **Date**: 2026-11-03
> **Design Doc**: [kb-document-management.design.md](../02-design/features/kb-document-management.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | S1의 "업로드 → 저장 상태 확인" 뒤에 되돌리기 단계가 없어 P2가 컬렉션 화면이나 DB로 우회해야 한다. |
| **WHO** | P2(KB 운영자·에이전트 소유자). 삭제 주체는 KB 소유자, ADMIN, 문서 업로더. |
| **RISK** | 삭제는 되돌릴 수 없다. 권한 판정 오류, 저장소 부분 실패로 인한 고아 청크, 요약 잡과의 경합이 주요 위험이다. |
| **SUCCESS** | 실제 Qdrant·ES·MySQL에서 삭제 후 해당 `document_id`의 데이터 0건, 권한 없는 사용자 403, 저장소 실패 시 메타데이터 유지 후 재시도 성공, 미인증 컬렉션 삭제 거부. |
| **SCOPE** | KB 문서 단건 삭제(백엔드+프론트) + 컬렉션 문서 삭제 DELETE 2개 인증 전환. KB 삭제 벡터 정리·일괄 삭제·조회 API 인증은 제외. |

---

## Strategic Alignment Check

PRD는 없다. 원천은 `docs/proposals/2026-10-15.md` §2-4와 `docs/USER-SCENARIOS.md` S1이다.

| 요소 | 기대 | 상태 |
|------|------|:----:|
| 핵심 문제 | P2가 KB 화면에서 업로드를 되돌릴 수 있다 | ✅ |
| 대상 사용자 | P2. 소유자·ADMIN·업로더만 삭제 | ✅ |
| 가치 | DB·Swagger 조작 없이 삭제하고 검색에서 제외 | ✅ (API 실런) · ⚠️ 브라우저 육안 확인 이월 |

### Success Criteria Status

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | 실저장소 삭제 후 해당 문서 0건, 다른 KB 문서 유지 | ✅ | L3 실런: 삭제 전 Qdrant 4·ES 4·메타 1 → 0·0·0, 잡 행 0. 같은 컬렉션 다른 KB 문서 4·4·1 유지 |
| SC-2 | 권한 표별 기대 상태 코드 | ✅ | `tests/api/test_knowledge_base_document_delete.py` (실제 가드·정책·UseCase 조립, TestClient) |
| SC-3 | ES 실패 시 메타 유지·5xx, 복구 후 재시도 성공 | ✅ | L3 실런: 503, Qdrant 0·ES 4·메타 1, 목록 유지 → 재시도 200, 전부 0 |
| SC-4 | 진행 중 잡 409, stale 잡 삭제 | ✅ | L3 실런: `processing` 잡 409·데이터 불변, `updated_at` 2시간 전으로 변경 후 200 |
| SC-5 | 무토큰 위조 헤더 401, 토큰 삭제 정상 | ✅ | L3 실런: 위조 헤더 401·데이터 불변, 토큰 200. 단위 `tests/api/test_doc_browse_delete_auth.py` |
| SC-6 | 브라우저에서 업로드 → 삭제 → 상태 해제 | ⚠️ | 페이지 테스트(`index.test.tsx` 5건)로 흐름 검증. 실제 브라우저 확인은 사용자 결정으로 이월(8000·5173 개발 서버 교체 필요) |
| SC-7 | 삭제 후 리트리버 테스트에서 제외 | ✅ | L3 실런: 삭제 전 검색 노출 → 삭제 후 미노출, 다른 문서는 노출 |

**Success Rate**: 6/7 충족, 1건 부분 충족(이월)

### Decision Record Verification

| 출처 | 결정 | 준수 | 편차 |
|------|------|:----:|------|
| [Plan] | 삭제 권한: 소유자·ADMIN·업로더 | ✅ | `policy.py:81-95` |
| [Plan] | 요약 잡 진행 중 409, stale 제외 | ✅ | KB UseCase `_ensure_not_busy` |
| [Plan] | 저장소 실패 시 메타 유지·재시도 | ✅ | `_purge_stores_strict` |
| [Plan] | 컬렉션 DELETE 2개 인증 전환 | ✅ | `doc_browse_router.py:142-183` |
| [Design] | Option C, 기존 메서드 무변경 | ✅ | `execute_single`·`execute_batch` 변경 없음, 기존 테스트 줄 삭제 0 |
| [Design] | 메타·잡 행·활동 로그 1트랜잭션 | ✅ | `main.py` 팩토리가 같은 `session`으로 조립, 배선 테스트로 고정 |
| [Design] | `delete_verified` 호출 1곳 | ✅ | AST 계약 테스트 |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 대비 구현의 구조·기능·계약 일치를 확인하고, 실저장소 실런으로 Plan Success Criteria를 판정한다.

### 1.2 Analysis Scope

- **Design**: `idt/docs/02-design/features/kb-document-management.design.md`
- **구현**: worktree `../wt/kb-document`의 `idt/src`, `idt/tests`, `idt_front/src` 변경분
- **정적 분석**: gap-detector 에이전트(Design·Plan과 코드만 전달, 구현 의도는 전달하지 않음)

---

## 2. Gap Analysis

### 2.1 API Endpoints

| Design | 구현 | 상태 |
|--------|------|:----:|
| DELETE `/api/v1/knowledge-bases/{kb_id}/documents/{document_id}` | `knowledge_base_router.py:506-544` | ✅ |
| GET `/api/v1/knowledge-bases/{kb_id}/documents` + `can_delete` | router `:198`, `:496` | ✅ |
| DELETE `/api/v1/collections/{name}/documents/{id}` Bearer 전환 | `doc_browse_router.py:142-154` | ✅ |
| DELETE `/api/v1/collections/{name}/documents` Bearer 전환 | `doc_browse_router.py:171-183` | ✅ |

### 2.2 Data Model

스키마 변경 0건. 값 객체 3개에 필드를 추가했다(`KbDocumentSummary.user_id`, `KbDocumentContext.kb`·`uploader_id`, `KbDocumentItem.can_delete`). Design §3과 일치한다.

### 2.3 Component Structure

| Design 구성요소 | 구현 | 상태 |
|------------------|------|:----:|
| `KbDocumentTable` 관리 열 | `KbDocumentTable.tsx:78-80`, `:119-139` | ✅ |
| `DeleteKbDocumentDialog` | 신규 `DeleteKbDocumentDialog.tsx` | ✅ |
| `KnowledgeBaseDetailPage` 상태 | `index.tsx` | ✅ |
| `useDeleteKbDocument` | `useKnowledgeBases.ts:82-93` | ✅ |

### 2.4 Functional Depth

FR-01~FR-13 모두 구현됨(파일·라인 근거는 gap-detector 보고 기준). 얕은 구현·플레이스홀더 0건.

### 2.5 Page UI Checklist

| 화면 | 항목 | 구현 | 누락 | 비율 |
|------|:----:|:----:|:----:|:----:|
| KnowledgeBaseDetailPage | 10 | 10 | 0 | 100% |

### 2.6 API Contract

| # | 엔드포인트 | Design | 서버 | 클라이언트 | 결과 |
|---|-----------|:------:|:----:|:----------:|:----:|
| 1 | KB 문서 DELETE | ✅ 필드 6 | ✅ | ✅ 타입·상수·서비스 | PASS |
| 2 | KB 문서 목록 GET `can_delete` | ✅ | ✅ | ✅ 필수 필드 | PASS |
| 3 | 컬렉션 DELETE 단건 | ✅ | ✅ | ✅ authApiClient | PASS |
| 4 | 컬렉션 DELETE 일괄 | ✅ | ✅ | ✅ authApiClient | PASS |

**Contract Match Rate**: 4/4 = 100%

### 2.7 Runtime Verification

#### L1: API (TestClient 실요청)

| 대상 | 결과 |
|------|------|
| KB 삭제 판정 표 23건 + 목록 1건 + 무토큰 1건 | 통과 |
| 컬렉션 삭제 인증 10건 | 통과 |
| 배선 테스트 2건 | 통과 |
| 실제 앱 스모크(무토큰 401, 없는 KB·문서 404, 목록 `can_delete`) | 통과 |
| 백엔드 전체 회귀 | master 기준선 실패 60건 대비 신규 실패 0건 |

**L1 Score**: 100%

#### L2: UI 동작 (Vitest + RTL + MSW, Playwright 미사용)

| 대상 | 결과 |
|------|------|
| 표·다이얼로그·훅·페이지 신규 테스트 | 통과 (KB 관련 14개 파일 84건) |
| 프론트 전체 | 실패 9건 4개 파일, 모두 기존 상시 실패. 수정 파일 0 |
| `tsc -b` | 오류 210 → 210, 신규 0 |
| 빌드 | 통과 |

**L2 Score**: 100%

#### L3: 실저장소 시나리오 (인프로세스 실제 앱 + 로컬 MySQL·Qdrant·ES)

| # | 시나리오 | 결과 |
|---|----------|------|
| 1 | S1 되돌리기 | ✅ API 수준. 브라우저 육안 확인은 이월 |
| 2 | 다른 문서 보존 | ✅ |
| 3 | 검색 제외 | ✅ |
| 4 | 부분 실패 복구 (ES 삭제만 인프로세스 실패) | ✅ |
| 5 | 요약 잡 409·stale 허용 (잡 행 직접 삽입) | ✅ |
| 6 | 컬렉션 경로 위조 헤더 401·토큰 삭제 | ✅ |

일회용 자원(컬렉션 1, KB 2, 문서 3)은 정리 후 잔여 0건을 확인했다. KB 행 2개는 기존 정책대로 soft-delete 상태로 남는다.

**L3 Score**: 5.5/6 = 92% (시나리오 1의 브라우저 확인 0.5 감점)

**Runtime Match Rate**: 100×0.4 + 100×0.3 + 92×0.3 = **97.6%**

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%                │
│  Functional Match Rate:   97%                │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:      97.6%              │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      98.5%              │
│  = 100×0.15 + 97×0.25 + 100×0.25 + 97.6×0.35 │
└─────────────────────────────────────────────┘
```

---

## 3. Code Quality Analysis

### 3.1 Findings

Critical·Important 0건. Minor는 다음과 같다.

| # | 내용 | 위치 | 판단 |
|---|------|------|------|
| M-1 | Design §3은 "kb.collection_name 내" 삭제로 적었지만 구현은 문서 메타데이터의 `collection_name`을 쓴다 | KB UseCase `:68` | 메타의 값이 문서가 실제로 저장된 컬렉션이므로 구현이 맞다. Design 문구를 고친다 |
| M-2 | Design §6.1은 403에 서버 메시지를 쓴다고 적었지만 구현은 403·404를 화면 문구로 바꾼다 | `index.tsx:19-31` | 서버 메시지가 영문이라 개선된 쪽이다. Design을 고친다 |
| M-3 | Design은 "기존 테스트 수정 없이"라고 적었다 | 기존 테스트 7개 파일 | diff 확인 결과 추가만 있고 삭제 줄 0. 해소 |
| M-4 | `create_kb_document_delete_factory` 90줄 | `main.py:4488-4577` | 지역 import 위주이며 같은 파일의 기존 DI 팩토리와 같은 구조. 유지 |
| M-5 | application이 `SectionSummaryJobRepository`(infrastructure)를 직접 import | KB UseCase `:23-25` | Design §2.3에서 `SectionSummaryQueryUseCase` 선례로 허용. 위반 아님 |

### 3.2 Security

| 심각도 | 내용 | 상태 |
|--------|------|------|
| 해소 | 컬렉션 DELETE가 위조 헤더만으로 임의 문서를 삭제할 수 있던 문제 | 테스트 Red에서 재현 → 수정 → 실런 401 확인 |
| 잔존 | `doc_browse_router` GET 2개(문서 목록·청크 원문) 무인증 | 범위 밖. Report에서 후속 이월 |

---

## 4. Performance Analysis

신규 경로는 Qdrant·ES 클라이언트를 팩토리 생성 시 1회만 만든다. 요청마다 클라이언트를 만드는 기존 `_delete_document_uc_factory`는 이번 범위에서 손대지 않았다.

---

## 5. Test Coverage

Design §8.2 L1 #1~15, §8.3 L2 #1~7 시나리오 전부에 대응 테스트가 있다. 커버리지 수치는 측정하지 않았다.

---

## 6. Clean Architecture Compliance

- domain 변경분(`policy.py`, `schemas.py`)은 외부 import 없음.
- 라우터는 예외 매핑만 담당하고 권한 판단은 domain 정책에 있다.
- 저장소는 commit·rollback을 호출하지 않는다. 트랜잭션은 `get_session`이 관리한다.

---

## 7. Convention Compliance

- 신규 백엔드 함수 모두 40줄 이내(`delete_verified` 40줄), if 중첩 2단 이내, `print()` 없음.
- 실패 로그는 `logger.error(..., exception=e, request_id=...)`로 스택 트레이스를 남긴다.
- 신규 프론트 코드에 hex 색상·`text-[Npx]` 없음. `IconButton`·디자인 토큰 사용. 컴포넌트 파일의 런타임 export 없음.

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Match Rate: 98.5%                   │
├─────────────────────────────────────────────┤
│  Critical 0 · Important 0 · Minor 5(1 해소)  │
│  Success Criteria 6/7 (+1 부분, 이월)         │
└─────────────────────────────────────────────┘
```

---

## 9. Recommended Actions

### 9.1 이번 사이클

| 항목 | 위치 |
|------|------|
| Design §3·§6.1 문구를 구현에 맞게 수정 (M-1, M-2) | Design 문서 |

### 9.2 후속 이월

| 항목 | 메모 |
|------|------|
| SC-6 브라우저 육안 확인 | 8000·5173 개발 서버를 worktree 코드로 교체한 뒤 확인 |
| 실제 섹션 요약 포인트가 있는 문서의 삭제 실런 | 요약 프로파일 KB 필요(LLM 호출) |
| `doc_browse_router` GET 2개 인증 | 문서 목록·청크 원문 무인증 조회 |
| `kb-vector-cleanup` | KB soft-delete 후 벡터 정리 |

---

## 10. Design Document Updates Needed

- [x] §3 삭제 대상 표: Qdrant 조건을 "문서 메타데이터의 `collection_name`"으로 수정 (Design v0.2)
- [x] §6.1: 403·404는 화면 문구로 바꾸고 409·503은 서버 메시지를 쓴다고 수정 (Design v0.2)

---

## 11. Next Steps

- [x] Design 문구 수정
- [ ] 완료 보고서 작성 (`/pdca report kb-document-management`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | 최초 분석 | 배상규 + Claude |
