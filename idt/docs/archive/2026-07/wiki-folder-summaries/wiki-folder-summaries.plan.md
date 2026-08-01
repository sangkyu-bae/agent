# wiki-folder-summaries Plan

> **Status**: draft
> **Created**: 2026-07-25
> **Feature**: wiki-folder-summaries
> **선행 기능**: wiki-agentic-navigation (아카이브, Match 100%) — 본 기능은 plan §9.1 후속 진화 1단계

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 위키 목차 주입(wiki-agentic-navigation)은 flat 목록이라 승인 위키가 늘면 상한(`wiki_toc_max_items=50` / `max_bytes=4000`)에 걸려 잘리고, LLM은 잘린 뒷부분의 존재 자체를 모른다. 문서 단위 나열은 건수가 늘수록 프롬프트 비용도 선형 증가한다. |
| **Solution** | 판단·요약을 **쓰기 시점**으로 옮긴다 — 문서 승인/편집/폐기 시 해당 폴더(path) 설명을 LLM으로 증류해 저장하고 상위 폴더로 전파. 목차 블록은 "폴더 설명 목록"으로 교체하고, `wiki_list(path)` 도구로 폴더 진입 → 문서 목록 → `wiki_read` 뎁스 탐색 체인을 완성한다. |
| **Function UX Effect** | 위키가 수백 건이어도 프롬프트에는 폴더 요약 십수 줄만 상주. 에이전트는 "지도 → 구역 → 문서" 순서로 사람처럼 탐색하며, 탐색 전 과정이 `ai_tool_call`(wiki_list/wiki_read)에 자동 기록돼 결정적으로 관측된다. |
| **Core Value** | 라우팅 검색 4부작(청킹→섹션→문서 요약→라우팅)의 "쓰기 시점 요약 계층" 설계 사상을 위키에 적용 — 질의 시점 비용은 상수로 고정하고, 요약 품질은 승인 이벤트마다 갱신되는 구조. deep-wiki-research(병렬 fan-out)로 가는 중간 골격. |

---

## 1. 배경

### 1.1 착수 트리거 점검

Plan §9.1(wiki-agentic-navigation)의 착수 트리거는 "승인 위키가 목차 상한에 걸리기
시작할 때"였다. 현재 실측치는 DB 미기동으로 미확인이며, **트리거 실측 전 선행 착수는
사용자 결정**(2026-07-25). 단, 상한 초과 여부와 무관하게 flat 목차의 바이트 비용은
위키 성장과 함께 선형 증가하므로 구조 전환의 방향 자체는 확정 상태다.

### 1.2 현재 구조 (선행 기능이 만든 골격)

```
[compile 시점]
WorkflowCompiler ── WikiTocProvider.render_block(agent_id)
                     └─ list_searchable_tree_items() → render_wiki_toc_block()
                        → "- (id: ..) {path}/{title} — 갱신 {date}" flat 목록
                        → supervisor prepend + wiki_read 워커 prompt 이중 주입 (D1)
[런타임]
wiki_read(article_id) → agent_id 격리 + is_searchable 검증 → 본문 반환
```

- `WikiArticle.path`: 가상 폴더 경로("여신/한도"), `WikiPolicy` 제약 —
  최대 깊이 3, 세그먼트 30자, 전체 255자, None=미분류 (wiki-user-facing V051)
- 증류 선례: `WikiDistiller`(문서→위키), `FeedbackDistiller`(👎→초안) — LLM 증류 +
  best-effort 패턴 기존 2종
- 승인 게이트: `WikiReviewUseCase.approve/edit/deprecate/restore` — 모든 상태 전이의
  단일 통로 (폴더 요약 재생성 훅 지점)

## 2. 목표

1. **쓰기 시점 폴더 요약 계층**: 위키 상태 전이(승인/편집/폐기/복구) 시 해당 path의
   폴더 설명을 증류·저장하고 상위 폴더로 전파(깊이 최대 3이므로 전파도 최대 2단)
2. **목차 블록의 폴더 모드**: 문서 flat 목록 대신 "폴더 경로 + 설명 + 문서 수" 목록
   렌더 — 프롬프트 상주 비용을 문서 수와 무관하게 고정
3. **`wiki_list(path)` 도구**: 폴더 진입 — 하위 폴더 요약 + 소속 문서(id/title/갱신일)
   목록 반환. `wiki_read`와 동일한 agent_id 격리·RunContext 패턴
4. **무회귀 점진 전환**: 승인 위키가 적을 때(임계 이하)는 기존 flat 목차 유지 —
   폴더 요약이 없거나 실패해도 기존 경로가 그대로 동작(폴백)

## 3. 스코프

### 3.1 In Scope

- `wiki_folder_summary` 저장 모델 + Flyway 마이그레이션 1건 (agent_id, path, summary,
  article_count, updated_at)
- 폴더 요약 증류 유스케이스(승인 이벤트 훅, best-effort — 승인 응답 차단 금지)
- `wiki_list` 도구 (TOOL_REGISTRY 등록 → 카탈로그 자동 동기화, 선행 기능과 동일)
- `render_wiki_toc_block` 폴더 모드 + flat 폴백 분기
- 워커 지시(`_WIKI_WORKER_INSTRUCTION`) 갱신: 폴더 설명 → `wiki_list` → `wiki_read` 체인
- TDD: 각 레이어 신규 테스트 (Red → Green)

### 3.2 Out of Scope (비스코프)

- **deep-wiki-research**: 병렬 fan-out + map-reduce 종합 — 폴더 계층 도입 후 수요 실측 시
- **wiki-knowledge-promotion**: 에이전트 간 지식 승격 — 중복 축적 사례 확인 시
- **wiki-usage-attribution**: 인용 강제·groundedness — 별도 후속
- general_chat 경로 확장 (custom agent 경로 한정 유지)
- 미분류(path=None) 문서의 자동 분류 — 미분류는 "(미분류)" 가상 폴더로만 취급
- 프론트엔드 변경 (백엔드 전용 — 폴더 요약의 UI 노출은 후속)

## 4. 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|:---:|
| FR-01 | `wiki_folder_summary` 테이블 + SQLAlchemy 모델 + Flyway V0xx (agent_id+path 유니크) | P0 |
| FR-02 | 폴더 요약 증류: 상태 전이 시 해당 path 재증류 + 상위 path 전파, LLM 실패는 warning 로그 + 기존 요약 유지(best-effort) | P0 |
| FR-03 | `wiki_list(path)` 도구: 하위 폴더(요약 포함) + 소속 문서 목록, agent_id 격리, 미존재/타 에이전트 path는 단일 실패 문구(오라클 차단 — wiki_read 관례) | P0 |
| FR-04 | 목차 블록 폴더 모드: 폴더 요약 목록 렌더 + "wiki_list로 진입" 지시. 승인 문서 수 ≤ 임계(config)면 기존 flat 목차 유지 | P0 |
| FR-05 | 워커 지시 갱신 + 이중 주입(supervisor/워커) 유지 — 폴더 모드에서도 D1 계약 보존 | P1 |
| FR-06 | 관측 배선 0 확인: wiki_list 호출이 `ai_tool_call`에 자동 기록(UsageCallback 기존 경로) | P1 |
| FR-07 | E2E 수동 검증 시나리오 정의(폴더 진입 체인) — 실행은 공통 이월 관례(ops/e2e-carryover-checklist) | P2 |

## 5. 아키텍처 방향 (Design에서 확정할 결정)

| 결정 항목 | 후보 | 비고 |
|-----------|------|------|
| 요약 저장 위치 | **신규 테이블 wiki_folder_summary** vs wiki_article 특수 행 | 신규 테이블 권장 — 라이프사이클(승인 게이트 없음)·불변식(source_refs)이 문서와 다름. wiki_article 오염 방지 |
| 재증류 트리거 방식 | approve/edit/deprecate/restore 훅 (동기 best-effort) vs 백그라운드 큐 | 훅+best-effort 권장 — 팬아웃 선례(wiki-feedback-loop) 재사용, 인프라 추가 0 |
| 폴더 모드 전환 기준 | 승인 문서 수 임계(config) vs 무조건 폴더 모드 | 임계 권장 — 위키 3건인 에이전트에 폴더 계층은 과설계. 독립 config 신규 추가(기존 값 변경 금지 — additive 관례) |
| 상위 전파 요약 입력 | 하위 폴더 요약들 vs 소속 문서 전문 | 하위 요약 입력 권장 — RAPTOR식 계층 증류, 토큰 상한 안정 |
| wiki_list 반환 포맷 | 텍스트 렌더 vs JSON | 텍스트 렌더 권장 — wiki_read `_render_article` 관례와 통일 |
| 미분류 처리 | "(미분류)" 가상 폴더 | path=None 문서도 탐색 가능해야 함 — 유실 금지 |

**예상 주요 변경 파일**: `domain/wiki/`(폴더 요약 엔티티·정책), `application/wiki/`
(folder_summary 유스케이스·provider 확장), `infrastructure/wiki/`(모델·repo·wiki_list_tool·
증류기), `domain/agent_builder/tool_registry.py`, `infrastructure/agent_builder/tool_factory.py`,
`application/agent_run/prompt_rendering.py`, `application/agent_builder/workflow_compiler.py`,
`src/config.py`, `src/api/main.py`, `db/migration/V0xx__create_wiki_folder_summary.sql`

## 6. 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 승인 시 LLM 증류 호출로 승인 API 지연 | 운영자 UX 저하 | best-effort 비차단(실패 시 기존 요약 유지) + 타임아웃, Design에서 동기/비동기 확정 |
| 폴더 요약이 stale(증류 실패 누적) | 탐색 오도 | updated_at 노출 + wiki_list가 항상 실시간 문서 목록을 반환(요약은 힌트, 목록이 진실) |
| 마이그레이션 배포 누락 | 신규 테이블 부재로 기동 실패 | FK CHARSET/COLLATE 명시 금지(V037 선례) + ops/migration-deploy-deps 등재 |
| 이중 주입 계약 파손 | 워커가 폴더 지도 못 봄 | 선행 기능 D1 테스트(test_workflow_compiler_wiki_toc) 폴더 모드 케이스 추가 |
| flat→폴더 전환 회귀 | 기존 소규모 에이전트 동작 변화 | 임계 이하 flat 유지 + 기존 테스트 전체 무수정 통과를 수용 기준에 포함 |

## 7. 검증 계획

- 단위(TDD): 폴더 요약 엔티티/정책, 증류 유스케이스(전파 포함), wiki_list 도구
  (격리·오라클 차단), 렌더 폴더 모드/폴백, compiler 주입 — 레이어별 Red→Green
- 회귀: 선행 기능 테스트 전체(flat 목차·wiki_read) 무수정 통과
- 관측: wiki_list의 `ai_tool_call` 기록을 조립 테스트로 단언 (배선 0 확인)
- E2E(이월): "○○ 폴더에 뭐 있어?" → wiki_list → wiki_read 체인 tool_call 실측 —
  Qdrant/MySQL 기동 시 공통 체크리스트와 일괄

## 8. Next Steps

1. [ ] `/pdca design wiki-folder-summaries` — §5 결정 항목 확정 (저장 모델·트리거 방식·임계 config·전파 입력)
2. [ ] 구현 (TDD)
3. [ ] `/pdca analyze wiki-folder-summaries`
4. [ ] 후속: deep-wiki-research (종합 질의 수요 실측 시)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-25 | Initial draft — wiki-agentic-navigation plan §9.1 후속 진화 1단계 착수 | 배상규 |
