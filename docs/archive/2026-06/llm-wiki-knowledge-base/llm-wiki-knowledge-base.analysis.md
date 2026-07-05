---
template: analysis
version: 1.2
feature: llm-wiki-knowledge-base
date: 2026-06-30
author: 배상규
project: sangplusbot
---

# llm-wiki-knowledge-base Analysis Report (v0.3, Full-stack)

> **Analysis Type**: Gap Analysis (PDCA Check, 3차 — 풀스택 전체)
>
> **Project**: sangplusbot
> **Analyst**: 배상규 (gap-detector agent 보조)
> **Date**: 2026-06-30
> **Design Doc**: [llm-wiki-knowledge-base.design.md](../02-design/features/llm-wiki-knowledge-base.design.md)

---

## 1. Analysis Overview

Phase 1(B 정제) + Phase 2(C 거버넌스)가 **백엔드 + 프론트 + 런타임 검색 와이어링(Step6) + `use_wiki_first` 양방향 계약**까지 풀스택으로 구현된 시점의 재평가. Phase 3(A 자가진화)와 위키 본문 ES BM25 색인은 의도적 미착수(PLANNED).

---

## 2. Match Rate

```
┌─────────────────────────────────────────────────────────────┐
│  Scoped Match Rate (Phase 1+2 풀스택 + Step6 + 계약):  ~98% ✅ │
│   (v0.3 94% → 상세/편집 UI·LOW 항목 마감 후 v0.4 ~98%)        │
│  Overall Completion (전체 설계, Phase 3 포함):         ~78% ⚠️ │
├─────────────────────────────────────────────────────────────┤
│  Architecture/DDD ~97%   API-Contract(BE↔FE) ~99%   컨벤션 ~98% │
└─────────────────────────────────────────────────────────────┘
```

> **v0.4 마감 항목**: ① `WikiDetailPanel`(본문 미리보기 + source_refs + 편집) 구현, 행클릭 진입, 죽어있던 `useUpdateArticle` 연결 ② reviewer/editor 빈값 시 거버넌스·저장 버튼 비활성 가드 ③ 상태 필터 한글 라벨. 프론트 wiki 테스트 15건 전부 통과(+ WikiDetailPanel 3건 신규).

추이: 백엔드 6스텝 95%(v0.1) → 백엔드 전체 83%→수정후 92%(v0.2) → **풀스택 94%(v0.3)**. Overall 57%→75%(프론트+와이어링 반영). 잔여 결손의 대부분은 Phase 3 + 위키 본문 ES 색인.

---

## 3. Targeted Verification (모두 통과 ✅)

| 검증 항목 | 결과 |
|-----------|:----:|
| RunScopedWikiSearch가 `execute(request, request_id)` 시그니처 유지(tool 무수정) | ✅ |
| RunContext에서 agent_id 해석, 없으면 inner 폴백 | ✅ |
| 호출마다 session_factory로 세션 오픈(싱글톤 안전, RunTracker 패턴) + lazy inner getter | ✅ |
| `_select_search`: use_wiki_first AND wiki_search 있을 때만 위키, 기본 불변 | ✅ |
| use_wiki_first 라운드트립: domain VO + app schema + FE type + 토글 + `RagToolConfig(**tool_config)` | ✅ 키 불일치 없음 |
| FE WikiArticle ↔ BE WikiArticleResponse 필드 완전 일치(editor/reviewer string\|null, 리터럴) | ✅ |
| 엔드포인트 8개 + 메서드(POST/GET/PATCH/PUT) 일치, authApiClient(Bearer), wiki.all invalidate | ✅ |
| WikiPage agent_id 게이트 + admin 전용 라우트 | ✅ |
| 빈 status/max_articles 생략 시 422 없음 | ✅ |
| main.py 부팅(팩토리3+override3 + RunScopedWikiSearch + ToolFactory wiki_search) | ✅ |

---

## 4. Gaps Found

### 🔵 부분 구현 (in scope)
| 영역 | 설계 | 구현 | 심각도 |
|------|------|------|:------:|
| 위키 상세/편집 UI | §5.1/§5.3 `WikiDetailPanel`(본문 미리보기·source_refs 링크·[편집]) | `useUpdateArticle` 훅·서비스·엔드포인트는 존재하나 **이를 호출하는 UI 없음**, 상세 패널/행클릭/본문/source_refs 미렌더. 테이블은 제목/상태/출처/신뢰도/액션만 | **MED** |
| 컴포넌트 위치 | §5.3 `src/components/wiki/` | `src/pages/WikiPage/` | LOW(FE 페이지 컨벤션상 허용) |
| 상태 필터 라벨 | 한글 라벨(`WIKI_STATUS_LABELS`) 보유 | 드롭다운이 enum 원값을 라벨로 사용 | LOW(UX) |

### 🟡 신규 코드 리스크 (전부 LOW)
| 항목 | 내용 |
|------|------|
| reviewer_id 빈문자 폴백 | `user?.id` 없으면 `reviewerId=''`; `ReviewActionRequest.reviewer_id`에 min_length 없음 → 빈 reviewer 저장 가능(실질적으로 AdminRoute로 보호됨). 버튼 비활성 또는 min_length=1 권장 |
| 폴백 시 세션 비용 | 위키 0건 폴백에도 MySQL 세션 1회 오픈(읽기전용·소량 오버헤드) |
| 컨벤션 긴장 | RunScopedWikiSearch가 session_factory로 세션 직접 생성(CLAUDE.md §6 인접) — 싱글톤 tool은 Depends 불가, RunTracker 동일 패턴 → 승인된 예외로 문서화 |

신규 코드에 HIGH/MED 결함 없음. v0.2 수정(update load-then-mutate, RBAC) 유지됨.

---

## 5. Recommendations

**Scoped 갭 마감 (~98%로)**
1. `WikiDetailPanel` 구현(본문 미리보기 + source_refs 링크 + 편집 폼) + `useUpdateArticle` 연결, `WikiArticleTable` 행클릭/확장. **유일한 의미 있는 in-scope 결손**
2. `reviewerId === ''`일 때 거버넌스 액션 가드(버튼 비활성) 또는 `ReviewActionRequest.reviewer_id` min_length=1

**폴리시(LOW)**
3. 상태 필터 드롭다운 라벨에 `WIKI_STATUS_LABELS[s].label` 사용

**문서 싱크(v0.2 §10 이월 — 설계 미반영)**
- §4.1 `/api/wiki`→`/api/v1/wiki`, restore 추가(7→8) / §4.2 distill 동기 계약으로 통일 / §6.2 에러 envelope 정책 / §3.3 VARCHAR(36) / §5.3 컴포넌트 경로

**다음 단계(Overall)**
- Phase 3(A): wiki_writer 노드·WikiWriteBackUseCase·confidence 환류(ai_retrieval_source)·valid_until TTL 배치 + 위키 본문 ES BM25 색인 (정상 out-of-scope)

---

## 6. 판정

Scoped **~94% (≥90%)** — Phase 1+2 풀스택은 **보고서 작성 가능 상태**. 상세 패널 UI(권장 1) 마감 후 `/pdca report`, 또는 Phase 3 진행. 추가 자동개선(iterate) 불필요.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | 백엔드 6스텝 순수 로직 (95%) | 배상규 |
| 0.2 | 2026-06-30 | 백엔드 전체(83%→수정후 92%): HIGH(update)·MED(RBAC) 수정 | 배상규 |
| 0.3 | 2026-06-30 | 풀스택 재평가(94%): Step6 와이어링 + 프론트 + use_wiki_first 계약 | 배상규 |
| 0.4 | 2026-06-30 | 상세/편집 UI(WikiDetailPanel) + LOW 항목 마감 → scoped ~98% | 배상규 |
