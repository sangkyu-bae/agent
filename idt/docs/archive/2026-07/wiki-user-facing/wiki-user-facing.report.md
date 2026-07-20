# wiki-user-facing Completion Report

> **Feature**: LLM Wiki 사용자 노출 (소유자 직접 작성 + 지식 트리 + 답변 근거 링크)
> **Author**: 배상규
> **Period**: 2026-07-18 (Plan → Design → Do → Check → Report 당일 완결)
> **Final Match Rate**: **100%** (1차 97.1% → 갭 2건 당일 보강)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | wiki-user-facing |
| 기간 | 2026-07-18 (1일) |
| Match Rate | 1차 97.1% → **100%** (iteration 0회 — 갭 2건 즉시 보강) |
| 구현 규모 | 백엔드 12파일(신규 2) + 프론트 11파일(신규 4) + 마이그레이션 V051 |
| 테스트 | 백엔드 143 passed(신규 ~40케이스) · 프론트 신규 18 + 회귀 8 passed · tsc/eslint 클린 |

### 1.3 Value Delivered

| Perspective | Delivered |
|-------------|-----------|
| **Problem** | 위키가 관리자 전용(/admin/wiki)이라 에이전트 소유자가 핵심 지식을 직접 써넣을 수 없었고(생성 경로가 distill뿐), 일반 사용자는 에이전트가 무엇을 알고 어디서 근거를 가져왔는지 볼 수 없는 블랙박스 상태였다. |
| **Solution** | ① `POST /wiki` 소유자 직접 작성 — `HUMAN` enum 예약석 활용, 즉시 approved, 출처 불변식은 `human:{user_id}`로 완화 없이 충족 ② `path` 컬럼(V051) + `GET /wiki/tree` — 서버 그룹핑 + 프론트 `/` split 중첩 폴더 렌더 ③ `SourceCitation` 위키 배지 → `/knowledge/{id}` 문서 뷰 (백엔드 무변경, 기존 `source="wiki"` 마킹 활용). |
| **Function/UX Effect** | 소유자는 `/agents/{id}/knowledge`에서 지식 문서를 작성·분류·수정·폐기(human 문서만, 서버 can_manage 인가). 일반 사용자는 같은 트리를 읽기 전용 탐색하고, 채팅 답변의 "📖 위키 근거" 배지 클릭 한 번으로 출처 문서를 검증. distill 신규 문서는 컬렉션명으로 자동 분류. |
| **Core Value** | 에이전트가 "구성이 보이는 폴더"가 됨 — 비전 원칙 6(투명성) 갭 해소, 위키 가이드 §10 한계(human API 부재) 해소, 성장형 에이전트 지식 축에 세 번째 생성 경로(사람 직접 기여) 개통. 거버넌스는 "전파 범위" 기준으로 유지(admin 전용 승인 경로 무회귀). |

---

## 2. PDCA 사이클 요약

| 단계 | 산출물 | 핵심 결정/결과 |
|------|--------|---------------|
| Plan | `01-plan/features/wiki-user-facing.plan.md` | 3축 범위 확정, 전파 범위 기준 거버넌스, org 스코프·워크스페이스 뷰 후속 분리 |
| Design | `02-design/features/wiki-user-facing.design.md` | 이월 결정 6건 확정(즉시 approved·human: 출처·human만 소유자 편집·열람 현행·라우트 2종·서버 그룹핑) + 실코드 제약 5건(metadata 부재·chunk_id=article id·tree 선언 순서·user_id 필드·editor 인증 통일) |
| Do | 백엔드 12파일 + 프론트 11파일 + V051 | TDD Red→Green, admin 경로 무변경 + 소유자 분기 추가(독립 opt-in 선례) |
| Check | `03-analysis/wiki-user-facing.analysis.md` | gap-detector 97.1% → GAP-1(트리 계층 렌더)·GAP-2(출처/갱신일) 당일 보강 → 100%, Extra 0 |

## 3. 주요 구현 내역

**백엔드**: `WikiPolicy` 확장(validate_path 깊이3/세그먼트30·human_source_ref·can_manage 인가 매트릭스), `HumanWikiWriteUseCase`(생성/편집/폐기, wiki·agent repo 단일 세션), `WikiQueryUseCase.list_tree`+`list_tree_items`(본문 제외 경량 조회), distill 기본 path, `wiki_router`(POST 201·GET /tree 선언 순서 가드·PUT/deprecate 인가 전환·editor 인증 사용자 기록), main.py DI.

**프론트**: 계약 동기화(상수/타입/서비스/훅/queryKeys/MSW), `SourceCitation` 위키 배지(일반 출처 회귀 0), `KnowledgeArticlePage`(단독 뷰·출처·갱신일), `AgentKnowledgePage`(buildFolderTree 재귀 렌더·미분류 그룹·소유자 전용 폼·path 자동완성), App 라우트 2종.

## 4. 배운 점 (Lessons)

1. **예약석 확인이 설계를 반으로 줄인다** — `HUMAN` enum·`clamp_confidence`처럼 선행 기능이 남긴 확장 자리를 실코드로 확인한 것이 신규 테이블/워크플로 없이 기존 승인·검색·UI 전체 재사용으로 이어졌다.
2. **경로 파라미터 라우트 뒤에 정적 세그먼트 추가 시 선언 순서가 계약이다** — `/wiki/tree`는 `/{id}`보다 먼저 선언해야 하며, MSW 핸들러도 동일한 순서 규칙을 따른다. 회귀 테스트로 고정했다.
3. **인가 확장은 "경로 권한 완화 + 유스케이스 인가" 조합이 안전하다** — admin 전용 의존성을 제거하되 can_manage가 admin을 항상 통과시키므로 기존 동작 무회귀가 정책 함수 테스트로 보장된다.
4. **프론트 계약에 없는 백엔드 metadata는 UX 설계 제약이 된다** — DocumentSource에 metadata가 없어 배지 라벨을 고정 문구로 결정(백엔드 무변경 유지). 계약 확인을 설계 단계에서 한 덕에 구현 중 재작업이 없었다.

## 5. 이월 항목 (Next)

- **E2E 수동 검증** (V051 적용 + Qdrant 실기동): 작성 → `use_wiki_first` 검색 반영 → 근거 배지 → 문서 뷰 — KB 시리즈 공통 이월 체크리스트 합류
- **후속 feature 후보**: `agent-workspace-view`(프롬프트/도구 종합 열람 + 2단 공개), `fix-wiki-distill-dedup`(중복 검사), org 스코프 결정(비교 문서 §5-1 — 위키 scope 컬럼 vs agent_memory 담당)
- **병행 대기**: agent-memory Phase 1 (Plan 완료 상태)

---

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | 완료 보고서 — Match Rate 100%, 당일 전체 사이클 완결 | 배상규 |
