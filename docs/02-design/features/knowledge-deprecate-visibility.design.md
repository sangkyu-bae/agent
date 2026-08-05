# knowledge-deprecate-visibility Design Document

> **Summary**: 지식 트리 API의 deprecated 제외 필터 + 폐기 성공 시 프론트 선택 해제 설계
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-08-02
> **Status**: Draft
> **Planning Doc**: [knowledge-deprecate-visibility.plan.md](../../01-plan/features/knowledge-deprecate-visibility.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 폐기(deprecate) 성공 직후, 지식 페이지의 **트리에서 항목이 사라지고 본문 패널이 초기 상태로 복귀**한다.
- 서버가 최종 진실: 필터는 백엔드 SQL에 두고, 프론트는 화면 로컬 상태(selectedId) 정리만 담당한다.
- `draft`/`approved` 노출 정책과 관리자 WikiPage(list API) 흐름은 일절 변경하지 않는다.

### 1.2 Design Principles

- **선례 준수**: `list_searchable_tree_items`(wiki-agentic-navigation D7)와 동일하게 상태 필터를 repository SQL에 배치하고, 컴파일된 쿼리 문자열 테스트로 의미를 고정한다.
- **최소 변경**: WHERE 조건 1건 + 프론트 콜백 1건. API 계약(`WikiTreeResponse`)·스키마·마이그레이션 변경 없음.
- **TDD**: 백엔드·프론트 모두 실패 테스트 선행.

---

## 2. Architecture

### 2.1 변경 지점 다이어그램

```
[폐기 클릭]
AgentKnowledgePage ──PATCH /wiki/{id}/deprecate──▶ HumanWikiWriteUseCase.deprecate (변경 없음)
      │                                                approved→deprecated 전이 성공
      │ onSuccess (변경 ②)
      ├─ invalidateWiki() ...... 기존 유지 (['wiki'] 전체 무효화)
      └─ setSelectedId(null) ... 신규: 본문 패널 초기화
      ▼
GET /wiki/tree?agent_id=... (재조회)
      ▼
WikiArticleRepository.list_tree_items (변경 ①)
      WHERE agent_id = :a
        AND status != 'deprecated'   ← 신규 조건
```

### 2.2 Dependencies

| Component | Depends On | 변경 |
|-----------|-----------|------|
| `AgentKnowledgePage` (idt_front) | `useDeprecateArticle` 훅 | 호출부에 `onSuccess` 콜백 추가 |
| `useDeprecateArticle` (훅) | `wikiService.deprecate` | **변경 없음** (전역 invalidate 유지) |
| `QueryUseCase.list_tree` (application) | `repo.list_tree_items` | **변경 없음** (path 그룹핑만) |
| `WikiArticleRepository.list_tree_items` (infrastructure) | `WikiArticleModel` | WHERE 조건 1건 추가 |

---

## 3. Data Model

변경 없음. `wiki_article` 테이블·`WikiStatus` enum(draft/approved/deprecated)·`WikiTreeItem` 스키마 모두 그대로. 마이그레이션 0건.

---

## 4. API Specification

### 4.1 Endpoint 변경 요약

| Method | Path | 계약 변경 | 동작 변경 |
|--------|------|-----------|-----------|
| GET | `/api/v1/wiki/tree?agent_id=` | 없음 (`WikiTreeResponse` 동일) | 응답 items에서 `status == 'deprecated'` 제외 |
| PATCH | `/api/v1/wiki/{id}/deprecate` | 없음 | 없음 |
| GET | `/api/v1/wiki/{id}` | 없음 | 없음 (폐기 문서도 상태 무관 조회 유지 — 관리자·복원 경로용) |

응답 스키마가 동일하므로 `api-contract-sync`(프론트 타입 동기화) 불필요.

---

## 5. 구현 상세

### 5.1 변경 ① — 백엔드: `list_tree_items` 상태 필터

**파일**: `idt/src/infrastructure/wiki/wiki_repository.py` (202행 부근)

```python
async def list_tree_items(
    self, agent_id: str, request_id: str
) -> list[WikiTreeItem]:
    """지식 트리용 경량 목록 — 본문(content) 미조회, path·최신순 정렬.

    knowledge-deprecate-visibility: 폐기(deprecated) 문서는 지식 트리에서
    제외한다(복원은 관리자 WikiPage의 list API 소관). draft는 노출 유지.
    의미 변경 시 test_wiki_repository_tree가 쿼리 문자열로 고정.
    """
    stmt = (
        select(... 기존 6컬럼 동일 ...)
        .where(
            WikiArticleModel.agent_id == agent_id,
            WikiArticleModel.status != WikiStatus.DEPRECATED.value,  # ← 신규
        )
        .order_by(... 기존 정렬 동일 ...)
    )
```

- 후처리(파이썬 filter)가 아닌 SQL WHERE — 경량 쿼리 원칙 유지.
- `!=` 단일 조건만 사용 (`== APPROVED`로 쓰지 않는다 — draft 노출 회귀 방지, Plan FR-03).

### 5.2 변경 ② — 프론트: 폐기 성공 시 선택 해제

**파일**: `idt_front/src/pages/AgentKnowledgePage/index.tsx` (287행 부근)

```tsx
<LoadingButton
  isPending={deprecateMutation.isPending}
  pendingText="폐기 중…"
  onClick={() =>
    deprecateMutation.mutate(article.id, {
      onSuccess: () => setSelectedId(null),
    })
  }
  ...
>
```

- `mutate` 호출부 옵션의 `onSuccess`는 훅에 정의된 `onSuccess: invalidateWiki`와 **병행 실행**된다(TanStack Query 규약) — 훅은 수정하지 않는다.
- 실패 시에는 선택 유지(현행 동작) — 폐기 실패 표면화는 스코프 밖.

### 5.3 변경하지 않는 것 (가드레일)

| 항목 | 이유 |
|------|------|
| `useDeprecateArticle` 훅 | WikiPage(관리자)도 공유 — 훅에 선택 해제를 넣으면 타 화면 오염 |
| `list_searchable_tree_items` | 이미 APPROVED만 필터 (프롬프트 목차) |
| `QueryUseCase.list_tree` | 그룹핑 로직만 담당, 필터 정책은 repository SQL 계층 선례 유지 |
| GET `/wiki/{id}` detail | 폐기 문서 조회는 관리자 화면·복원에 필요 |

---

## 6. Error Handling

| 시나리오 | 동작 |
|----------|------|
| 폐기 PATCH 실패 (403/409/500) | 현행 유지 — mutation error, 선택·화면 유지. `onSuccess` 미실행이므로 부작용 없음 |
| 폐기 성공 + tree 재조회 실패 | 트리는 stale 데이터 표시(기존 TanStack 동작), 본문 패널은 초기화됨 — 수용 |
| 이미 deprecated인 문서에 재폐기 | 백엔드 `WikiPolicy.validate_transition`이 거부(기존 동작, 변경 없음) |

---

## 7. Security Considerations

- 인가 변경 없음 — 폐기는 기존 `can_manage`(admin 전부, 소유자는 human 문서만) 유지.
- 트리 필터 강화는 정보 노출을 **줄이는** 방향 (폐기 문서 메타데이터 미노출).

---

## 8. Test Plan (TDD — 구현 전 작성)

### 8.1 백엔드 (pytest)

**신규 파일**: `idt/tests/infrastructure/wiki/test_wiki_repository_tree.py`
(`test_wiki_repository_toc.py`의 쿼리 문자열 고정 패턴 미러)

| # | 테스트 | 검증 |
|---|--------|------|
| B1 | `test_query_excludes_deprecated` | 컴파일된 SQL에 `status != 'deprecated'` 포함 (literal_binds) |
| B2 | `test_query_keeps_agent_filter_and_path_order` | `agent_id` 필터·`path IS NULL` 후순위·`updated_at DESC` 정렬 유지 |
| B3 | `test_query_does_not_filter_draft` | SQL에 `'draft'` 부재 + `= 'approved'` 형태 부재 (FR-03 고정) |
| B4 | `test_lightweight_no_content_column` | SELECT 절에 `content` 부재 (경량 원칙 회귀 방지) |

**기존 파일 확인**: `tests/application/wiki/test_wiki_query_tree.py`·`test_wiki_repository_contract.py`는 fake repo 기반이라 무회귀 확인만.

### 8.2 프론트 (Vitest + RTL + MSW, `--pool=threads`)

**기존 파일 확장**: `idt_front/src/pages/AgentKnowledgePage/index.test.tsx`
(파일 내 `server.listen` 3종 훅 이미 선언됨 — per-file listen 규칙 충족)

| # | 테스트 | 시나리오 |
|---|--------|----------|
| F1 | 폐기 성공 시 본문 패널이 초기 문구로 복귀 | `loginAsOwner` → human 문서 선택 → 폐기 클릭 → `왼쪽 트리에서 문서를 선택하세요.` 표시 |
| F2 | 폐기 성공 시 트리에서 항목 제거 | PATCH 핸들러에서 `server.use`로 tree 응답을 해당 항목 제외본으로 교체 → 재조회 후 `queryByText` 부재 확인 |
| F3 | 폐기 실패 시 문서·선택 유지 | PATCH 500 오버라이드 → 본문 계속 표시 |

주의: F1·F2는 MSW mock 문서가 `source_type: 'human'` + `status: 'approved'`여야 폐기 버튼이 렌더된다(기존 mock `위키-w1` 확인 후 필요 시 핸들러 오버라이드).

### 8.3 수동 E2E (Do 이후 체크리스트)

- [ ] venv 기동(idt-server-must-run-on-venv) 후 실제 폐기 → 트리 즉시 제거 확인
- [ ] 관리자 WikiPage에서 폐기 문서가 status 필터로 조회·복원 가능 확인
- [ ] 복원 후 지식 트리에 재등장 확인

---

## 9. Clean Architecture — Layer Assignment

| 변경 | Layer | 파일 | 규칙 충족 |
|------|-------|------|-----------|
| status 필터 | Infrastructure | `idt/src/infrastructure/wiki/wiki_repository.py` | 비즈니스 규칙 아닌 조회 조건 — D7 선례와 동일 계층. domain/application 무변경 |
| 선택 해제 | Presentation (idt_front) | `src/pages/AgentKnowledgePage/index.tsx` | 화면 로컬 상태는 페이지 책임, 훅(공유 계층) 불변 |

- 금지 사항 위반 없음: 레이어 이동 없음, 스키마 변경 없음, 세션/트랜잭션 로직 무접촉.

---

## 10. Coding Convention Reference

- 백엔드: docstring에 정책 사유 + 테스트 고정 명시 (D7 주석 관례), config 하드코딩 없음(enum 값 사용)
- 프론트: 기존 import 순서·주석 스타일(`// knowledge-deprecate-visibility:` 접두) 유지

---

## 11. Implementation Guide

### 11.1 구현 순서

1. [ ] **B1~B4 테스트 작성** → Red 확인 (`idt/tests/infrastructure/wiki/test_wiki_repository_tree.py`)
2. [ ] `list_tree_items` WHERE 조건 추가 → Green
3. [ ] **F1~F3 테스트 작성** → Red 확인 (`index.test.tsx` 확장, `--pool=threads`)
4. [ ] `AgentKnowledgePage` mutate `onSuccess` 추가 → Green
5. [ ] 백엔드 wiki 테스트 전체 무회귀 (`pytest tests/infrastructure/wiki tests/application/wiki tests/api/test_wiki_router.py` — 교차 실행 산발 실패 시 격리 재실행)
6. [ ] 수동 E2E 체크리스트 (8.3)

### 11.2 예상 변경 파일

| 파일 | 종류 |
|------|------|
| `idt/src/infrastructure/wiki/wiki_repository.py` | 수정 (WHERE 1건 + docstring) |
| `idt/tests/infrastructure/wiki/test_wiki_repository_tree.py` | 신규 (테스트 4건) |
| `idt_front/src/pages/AgentKnowledgePage/index.tsx` | 수정 (onSuccess 1건) |
| `idt_front/src/pages/AgentKnowledgePage/index.test.tsx` | 수정 (테스트 3건 추가) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-02 | 초안 — 변경 2건·테스트 7건 설계 | 배상규 |
