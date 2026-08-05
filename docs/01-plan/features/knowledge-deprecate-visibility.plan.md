# knowledge-deprecate-visibility Planning Document

> **Summary**: 에이전트 지식 페이지(`/agents/{agentId}/knowledge`)에서 폐기(deprecate)한 문서가 트리와 문서 뷰에 계속 표시되는 결함 수정
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-08-02
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 지식 페이지에서 소유자가 "폐기"를 눌러도 문서가 트리·본문 패널에 그대로 남아, 폐기가 동작하지 않는 것처럼 보인다. 실제로는 서버에서 `approved→deprecated` 전이가 성공하지만 트리 API가 폐기 문서를 계속 내려준다. |
| **Solution** | 지식 트리 조회(`list_tree_items`)에서 `deprecated` 상태를 SQL WHERE로 제외하고, 프론트는 폐기 성공 시 선택(selectedId)을 해제해 본문 패널도 함께 정리한다. |
| **Function/UX Effect** | 폐기 클릭 → 트리에서 항목 즉시 사라짐 + 본문 패널이 안내 문구로 복귀. 사용자 행동과 화면 결과가 일치한다. |
| **Core Value** | P2(에이전트 소유자)의 지식 관리 신뢰성 — "폐기했는데 남아있다"는 오동작 인식 제거, 관리자 복원 경로(WikiPage)는 그대로 보존. |

---

## 1. Overview

### 1.1 Purpose

에이전트 지식 페이지의 폐기 버튼이 화면에 반영되지 않는 문제를 고쳐, 폐기 즉시 트리와 문서 뷰에서 해당 문서가 사라지게 한다.

### 1.2 Background — 원인 분석 (조사 완료)

증상: `AgentKnowledgePage`에서 폐기 버튼 클릭 → API는 200 성공 → 그러나 트리 항목과 열려 있던 문서가 그대로 표시됨.

조사 결과 **프론트 캐시 문제가 아니라 백엔드 트리 조회의 상태 필터 누락**이 원인이다.

| # | 확인 지점 | 결과 |
|---|-----------|------|
| 1 | `idt_front/src/hooks/useWiki.ts` — `useDeprecateArticle` | `onSuccess: invalidateWiki`로 `['wiki']` 프리픽스 전체 무효화. **정상** |
| 2 | `idt_front/src/lib/queryKeys.ts:150-156` | tree 키 = `['wiki','tree',agentId]` → 무효화 범위에 포함. **정상** (재조회는 일어남) |
| 3 | `idt/src/infrastructure/wiki/wiki_repository.py:202` `list_tree_items` | WHERE 절이 `agent_id`만 필터, **status 필터 없음** → deprecated 문서가 트리 응답에 계속 포함. **← 근본 원인** |
| 4 | 대조: 같은 파일 `list_searchable_tree_items` (165행) | 프롬프트 목차용은 `status == APPROVED` + 미만료를 SQL로 필터 (wiki-agentic-navigation D7 패턴) |
| 5 | `idt_front/src/pages/AgentKnowledgePage/index.tsx:287` | 폐기 성공 후 `selectedId` 미해제 → 본문 패널은 재조회된 폐기 문서를 배지만 바뀐 채 계속 렌더. **부차 원인** |

즉 폐기 전이(approved→deprecated)와 캐시 무효화·재조회는 모두 성공하지만, 재조회된 트리에 폐기 문서가 다시 들어 있어 화면이 변하지 않는다.

### 1.3 Related Documents

- 폐기 전이 로직: `idt/src/application/wiki/human_write_use_case.py:117` (`deprecate`, can_manage 인가)
- 트리 유스케이스: `idt/src/application/wiki/query_use_case.py:34` (`list_tree` — path 그룹핑만, 필터 없음)
- 선행 기능: wiki-user-facing (트리·폐기 버튼 도입), wiki-agentic-navigation (SQL 상태 필터 미러 패턴)
- 관리자 복원 경로: `idt_front/src/pages/WikiPage` — `/wiki` list API(status 필터 지원) 사용, tree API 미사용

---

## 2. Scope

### 2.1 In Scope

- [ ] **백엔드**: `list_tree_items`에 `status != deprecated` WHERE 조건 추가 (지식 트리에서 폐기 문서 제외)
- [ ] **백엔드 테스트**: deprecated 문서가 트리 응답에서 제외됨을 검증 (repository 단위 + tree 라우트)
- [ ] **프론트**: `AgentKnowledgePage` 폐기 성공 시 `selectedId` 해제(본문 패널 정리)
- [ ] **프론트 테스트**: 폐기 클릭 → 트리 재조회 후 항목 미표시 + 본문 패널 초기 문구 복귀 (MSW)

### 2.2 Out of Scope

- `draft` 문서의 트리 노출 정책 변경 — 현행 유지(초안도 트리에 표시, 상태 배지로 구분). 피드백 환류(wiki-feedback-loop)가 만드는 draft 가시성에 영향 주지 않기 위함
- 관리자 WikiPage의 폐기/복원 흐름 — list API 기반이라 이번 결함과 무관
- 프롬프트 목차(`list_searchable_tree_items`) — 이미 APPROVED만 필터, 변경 없음
- 지식 페이지에 복원(restore) 버튼 추가 — 복원은 관리자 WikiPage 소관 유지

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | GET `/wiki/tree` 응답에서 `deprecated` 상태 문서를 제외한다 (SQL WHERE, 후처리 아님) | High | Pending |
| FR-02 | 폐기 성공 시 프론트가 선택 문서를 해제해 본문 패널을 초기 상태("왼쪽 트리에서 문서를 선택하세요.")로 되돌린다 | High | Pending |
| FR-03 | `draft`·`approved` 문서의 트리 노출은 현행과 동일하게 유지된다 (회귀 금지) | High | Pending |
| FR-04 | 관리자 WikiPage에서 deprecated 문서 조회·복원이 기존대로 동작한다 (tree 미사용 확인) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 필터는 repository SQL에 배치, 의미 주석으로 `list_searchable_tree_items` D7 미러 패턴 준수 | 코드 리뷰 + verify-architecture |
| 성능 | 트리 응답 지연 회귀 없음 (WHERE 조건 1개 추가 수준) | 기존 wiki-tree-performance 기준(35ms) 유지 |
| 테스트 | TDD — 테스트 선행 작성 (backend pytest / frontend Vitest+MSW) | Red→Green 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 폐기 클릭 → 트리에서 항목 제거 + 본문 패널 초기화 (수동 E2E)
- [ ] 백엔드: deprecated 제외 검증 테스트 통과, 기존 wiki 테스트 무회귀
- [ ] 프론트: 폐기 시나리오 컴포넌트 테스트 통과 (`--pool=threads`)
- [ ] 관리자 WikiPage 폐기 목록·복원 무회귀

### 4.2 Quality Criteria

- [ ] 마이그레이션 0건 (스키마 변경 없음)
- [ ] API 스키마 변경 없음 → 프론트 타입 동기화 불필요 (응답 항목만 줄어듦)
- [ ] lint/빌드 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 트리에서 draft까지 제외해버리는 과필터 | Medium | Low | `!= deprecated` 단일 조건만 사용, FR-03 회귀 테스트로 고정 |
| 다른 소비자가 tree API로 deprecated를 기대 | Low | Low | 전수 조사 완료 — tree 라우트 소비자는 AgentKnowledgePage 단일, 관리자는 list API 사용 |
| 폐기 직후 detail 쿼리가 404/에러 처리 필요 | Low | Low | detail(GET /{id})은 상태 무관 조회 유지, 프론트는 selectedId 해제로 detail 자체를 안 띄움 |
| entity `is_searchable`류 의미와 SQL 이중 관리 표류 | Low | Medium | D7 선례처럼 미러 주석 + 쿼리 고정 테스트 추가 |

---

## 6. Architecture Considerations

기존 프로젝트 규칙 적용 (신규 결정 없음):

| Decision | Selected | Rationale |
|----------|----------|-----------|
| 필터 위치 | Infrastructure repository SQL (`list_tree_items`) | 본문 미조회 경량 쿼리 원칙 유지, `list_searchable_tree_items` 선례와 동일 계층 |
| 프론트 상태 정리 | `useDeprecateArticle().mutate(..., { onSuccess: 선택 해제 })` 또는 페이지 핸들러에서 처리 | 훅의 전역 invalidate는 유지, 화면 로컬 상태만 페이지에서 책임 |
| API 계약 | 변경 없음 (`WikiTreeResponse` 동일) | 응답에 포함되는 항목 집합만 축소 — `api-contract-sync` 불필요 |

- 레이어: domain 규칙 변경 없음, application(`list_tree`)은 그대로, infrastructure WHERE 1건 + interfaces 변경 없음
- DB 스키마·마이그레이션: 없음

---

## 7. Convention Prerequisites

- 기존 컨벤션 적용: `idt/CLAUDE.md`(TDD 필수, 함수 40줄, logger), `idt_front` MSW per-file listen 규칙
- 환경변수 추가: 없음
- 신규 파일: 없음 예상 (기존 파일 수정 + 테스트 추가)

---

## 8. Next Steps

1. [ ] `/pdca design knowledge-deprecate-visibility` — WHERE 절 위치·주석 규약, 프론트 선택 해제 지점, 테스트 목록 확정
2. [ ] TDD 구현 (backend → frontend)
3. [ ] `/pdca analyze knowledge-deprecate-visibility`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-02 | 원인 분석 포함 초안 | 배상규 |
