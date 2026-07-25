# wiki-agentic-navigation Gap Analysis Report

> **Design(SoT)**: `docs/02-design/features/wiki-agentic-navigation.design.md`
> **분석일**: 2026-07-23 (gap-detector 에이전트 수행 + Act 즉시 보강 1건 반영)
> **Match Rate**: **100%** (14/14 — 최초 99%, Low 갭 1건 즉시 해소)

---

## 1. 항목별 판정표

| # | 체크 항목 | 판정 | 근거 (파일:라인) |
|---|-----------|:----:|------------------|
| 1 | D1 목차 이중 주입 (supervisor prepend + wiki_read 워커 prompt) | ✅ | `workflow_compiler.py:193-194`(prepend), `:274-278`(워커 `prompt=`toc+지시); `test_workflow_compiler_wiki_toc.py` 양쪽 단언 |
| 2 | D2 agent_id kwarg additive·sub_agent 미전달·run_agent 전달 | ✅ | `workflow_compiler.py:159`, sub_agent 재귀 미포함, `run_agent_use_case.py:573` |
| 3 | D3/FR-07 metadata source==`wiki:{title}`·기존 키 보존 | ✅ | `wiki_first_search_use_case.py:78`; 테스트 단언 포함 |
| 4 | D4/FR-05 BaseTool + args_schema article_id (자동 tool_call 기록 전제) | ✅ | `wiki_read_tool.py:42,47,53` |
| 5 | D5/FR-01 TOOL_REGISTRY 등록 + `internal:wiki_read` 동기화 | ✅* | `tool_registry.py:54-63`; **최초 ⚠️(전용 단언 부재) → Act 보강**: `test_sync_internal_tools_use_case.py::test_wiki_read_included_and_policy_valid` 추가 (동기화 + ToolIdFormatPolicy 통과 고정) |
| 6 | D6 category ≠ search/analysis → react agent 경로 | ✅ | ToolMeta 기본 "action" → `_resolve_category` → react 분기; 테스트 고정 |
| 7 | D7 승인+미만료 SQL 미러·updated_at DESC·본문 미조회·기존 메서드 불변 | ✅ | `wiki_repository.py:174-192`; 쿼리 문자열 미러 테스트 |
| 8 | D8 config 상한 2종 + settings 주입 (하드코딩 없음) | ✅ | `config.py:18-19`, `main.py` DI |
| 9 | FR-02 가드 4분기 None 수렴 + 단일 실패 텍스트 + ctx 없으면 세션 미개방 | ✅ | `read_article_use_case.py:23-29`, `wiki_read_tool.py:64-77` |
| 10 | FR-03 목차 블록 형식 (헤더·사용지시·id·갱신일·절단·구분자) | ✅ | `prompt_rendering.py:58-111` + 8개 렌더링 테스트 |
| 11 | FR-04 0건→''·미선택/미주입/agent_id 없음→프롬프트 불변 | ✅ | 3중 가드 + 비활성 4케이스 테스트 |
| 12 | §1.2 컴포넌트 배치 표 ↔ 실제 파일 위치 | ✅ | 12개 전부 일치 |
| 13 | FR 매핑 표의 테스트 존재·단언 | ✅ | 9개 테스트 파일 + 보강 1건 |
| 14 | Out of Scope 준수 (벡터 경로 1키 외 무변경·general_chat 미접촉·마이그레이션 0) | ✅ | additive 확인, 마이그레이션 파일 0 |

## 2. Act 보강 (분석 직후 즉시 수행)

- **#5 Low 갭**: `internal:wiki_read` 카탈로그 동기화가 범용 순회 테스트에 암묵 의존
  → `tests/application/tool_catalog/test_sync_internal_tools_use_case.py`에 전용 단언 1건 추가
  (동기화 생성 + `ToolIdFormatPolicy.validate("internal:wiki_read", "internal")` 통과). 6/6 그린.

## 3. 추가 관찰 (gap 아님)

- 인터페이스 기본 메서드 `list_searchable_tree_items`는 `raise NotImplementedError` —
  기존 페이크 무회귀를 위한 additive 설계(Design 명시)이며, TocProvider가 best-effort로
  예외를 흡수하므로 미구현 저장소에서도 대화가 차단되지 않는다.

## 4. 테스트 실행 결과 (격리 실행, Windows flakiness 관례)

| 스위트 | 결과 |
|--------|------|
| application/wiki + infrastructure/wiki | 138 passed |
| application/agent_builder (전체) | 462 passed |
| application/agent_run + domain/infra agent_builder | 392 passed |
| application/rag_agent | 57 passed |
| application/tool_catalog (보강 후) | 6 passed |

배치 실행 중 setup OSError 다수 발생 → TIME_WAIT 소켓 1007개(소켓 고갈)로 확인,
드레인 후 재실행 전량 통과 — 코드 회귀 아님.

## 5. 이월 항목 (Match Rate 제외)

| 항목 | 상태 | 내용 |
|------|:----:|------|
| FR-08 E2E 수동 | ⏸ 이월 | Qdrant/MySQL 기동 + 승인 위키 2건 이상 전제. Design §6 시나리오 4종: ① "최근 결정사항" → wiki_read tool_call(`arguments.article_id`) 실측 ② 특정 문서 지정 열람 ③ 위키 0건 부정 케이스 ④ use_wiki_first 회귀 + `[출처: wiki:{title}]` 표기 |

## 6. 결론

Design-구현 일치 100% (품질 기준 90% 충족). Design이 코드 추적 기반으로 작성되어
설계-구현 표류가 사실상 0. 잔여는 FR-08 E2E 수동 검증뿐 — Report 단계 진행 가능.
