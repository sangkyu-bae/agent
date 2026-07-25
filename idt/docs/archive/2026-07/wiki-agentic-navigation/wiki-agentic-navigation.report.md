# wiki-agentic-navigation 완료 보고서

> **Project**: sangplusbot (idt 백엔드)
> **기간**: 2026-07-23 (Plan → Design → Do → Check → Report 당일 완결)
> **Author**: 배상규
> **Match Rate**: **100%** (최초 99% → Act 보강 1건 즉시 마감)
> **문서**: [Plan](../01-plan/features/wiki-agentic-navigation.plan.md) · [Design](../02-design/features/wiki-agentic-navigation.design.md) · [Analysis](../03-analysis/wiki-agentic-navigation.analysis.md) · [배경 분석](../llm-wiki-runtime-flow.md)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | wiki-agentic-navigation — 위키 목차 프롬프트 주입 + `wiki_read` 명시 열람 도구 |
| 기간 | 2026-07-23 (1일, PDCA 전 단계) |
| Match Rate | 100% (14항목 gap-detector 실측, 이터레이션 0회) |
| 규모 | 신규 3 파일 + 수정 11 파일, 신규 테스트 5 파일 + 확장 5 파일 (신규 단언 40+), 마이그레이션 **0**, 프론트 변경 **0** |

### 1.3 Value Delivered (4관점)

| 관점 | 전달 가치 |
|------|-----------|
| **Problem** | 위키 소비가 벡터 검색 단일 경로라 ① 에이전트가 자기 위키 전체상(목차·최근 결정)을 인지 못 하고 ② 위키가 원본 청크와 top_k 슬롯을 경쟁하며 ③ "읽었는지" 관측이 검색 로그 간접 추적뿐이고 ④ 위키 hit이 LLM에 `[출처: unknown]`으로 표시되는 결함까지 있었음 |
| **Solution** | 문서 탐색 계층 추가(교체 아님): `wiki_read` 내부 도구(승인+미만료+자기 agent_id만, 실패 사유 미노출 단일 수렴) + 승인 위키 목차 블록의 **이중 주입**(supervisor prepend + wiki_read 워커 react agent prompt — 워커 LLM이 목차를 못 보면 열람할 id를 모른다는 함정을 설계 단계에서 발견·해소) + 기존 벡터 경로 유지(출처 표기만 `wiki:{title}` 수정) |
| **Function/UX Effect** | "최근 결정사항 알려줘" 같은 구조적·시간적 질의가 목차 인지 → 문서 드릴다운으로 처리 가능. 운영자는 `ai_tool_call.arguments_json.article_id`로 **어떤 위키 문서를 읽었는지 문서 단위 결정적 확인** — 기존 UsageCallback 자동 기록에 무임승차라 관측 배선 0 |
| **Core Value** | 위키를 "검색 결과의 경쟁자"에서 "항상 참조 가능한 상위 지식 계층"으로 격상. 도구 선택 자체가 opt-in이라 신규 컬럼·마이그레이션 0, 카탈로그(`internal:wiki_read`)·관측성·프론트 전부 기존 인프라 자동 편승. 후속 진화 경로(폴더 요약→deep research→지식 승격)의 1단계 골격 확보 |

---

## 2. 구현 내역

### 2.1 신규 파일 (3)

| 파일 | 역할 |
|------|------|
| `src/application/wiki/read_article_use_case.py` | 열람 가드 — 미존재/타 에이전트/미승인/만료 전부 None 수렴 (id 오라클 차단) |
| `src/application/wiki/toc_provider.py` | compile 시점 목차 블록 생성 — per-call 세션, 실패 시 '' 폴백 (best-effort) |
| `src/infrastructure/wiki/wiki_read_tool.py` | `wiki_read` BaseTool — RunContext agent_id 격리, ctx 없으면 세션 미개방 |

### 2.2 수정 파일 (11)

tool_registry(메타 등록) · tool_factory(생성 분기+의존 2종, 미주입 조기 ValueError) ·
wiki_repository(`list_searchable_tree_items` — is_searchable SQL 미러·updated_at DESC·본문 미조회) ·
인터페이스(non-abstract 기본 메서드 — 기존 페이크 무회귀) ·
prompt_rendering(`render_wiki_toc_block` — id 병기·상한 2종·사용 지시) ·
workflow_compiler(ctor provider + `agent_id` kwarg + 이중 주입 + 워커 지시) ·
run_agent_use_case(compile에 agent.id) · wiki_first_search_use_case(`source="wiki:{title}"`) ·
config(상한 2종) · main.py(DI) · sync 테스트(카탈로그 단언 — Act 보강)

### 2.3 테스트

격리 실행 전량 통과: wiki 138 · agent_builder 462 · agent_run+domain+infra 392 · rag_agent 57 · tool_catalog 6.
배치 실행 중 setup OSError 다수는 TIME_WAIT 소켓 1007개(소켓 고갈)로 판명 — 코드 회귀 아님, 재실행 전량 통과.

---

## 3. 핵심 결정 회고 (D1~D8 중 값진 것)

| 결정 | 회고 |
|------|------|
| D1 이중 주입 | 설계 중 최대 발견 — supervisor 프롬프트에만 목차를 넣으면 정작 도구를 호출하는 워커 react agent가 목차를 못 봐 id 선택 불가. `create_react_agent`의 `prompt` 파라미터 지원을 시그니처 실측으로 확인 후 채택 |
| D4 관측 배선 0 | `UsageCallback.on_tool_start`가 모든 BaseTool을 자동 영속화함을 사전 확인 → "읽었는지 확인" 요구가 구현 없이 테스트 고정만으로 충족 |
| opt-in = 도구 선택 | 신규 컬럼/플래그 대신 도구 선택 메커니즘 재사용 → 마이그레이션 0·프론트 0·"독립 opt-in" 관례 부합 |
| Design의 코드 추적 선행 | compile async 여부·자동 기록·카탈로그 동기화를 Design 단계에서 실측 → 구현 표류 사실상 0 (Match 99→100%) |

## 4. 교훈 (Lessons Learned)

1. **프롬프트 주입은 소비자별로 검증하라** — supervisor와 워커는 프롬프트 컨텍스트가 분리된다. "주입했다"가 아니라 "그걸 읽는 LLM이 누구인가"를 물어야 한다 (D1 함정).
2. **관측성 요구는 기존 콜백 인프라부터 확인** — 새 기록 코드를 짜기 전에 on_tool_start 범용 훅 존재를 확인해 배선 0으로 해결.
3. **인터페이스 확장은 non-abstract 기본 메서드로** — abstractmethod 추가는 기존 페이크·구현체를 전부 깨뜨린다. additive 확장 + NotImplementedError 기본이 무회귀.
4. **바이트 상한은 "무엇의 상한인지" 테스트에 명시** — 목록부 상한 vs 전체 블록 상한 혼동으로 테스트 1회 실패. 고정 오버헤드(헤더)는 상한 밖임을 주석으로 고정.
5. **배치 pytest 에러는 소켓부터 의심** — TIME_WAIT 1007개 상태에서 setup OSError 40건 → 격리 재실행으로 전량 통과. 기존 "격리 실행" 관례의 원인이 소켓 고갈로 구체화됨.

## 5. 이월 항목

| 항목 | 내용 | 다음 액션 |
|------|------|-----------|
| FR-08 E2E 수동 | Design §6 시나리오 4종 (목차 질의→`article_id` 실측, 문서 지정 열람, 위키 0건 부정, use_wiki_first 회귀+출처 표기) | Qdrant/MySQL 기동 시 KB 파이프라인 E2E 체크리스트와 일괄 수행 |
| 후속 진화 경로 | wiki-folder-summaries(목차 상한 도달 시) → deep-wiki-research(종합 질의 수요 실측 시) → wiki-knowledge-promotion(중복 축적 확인 시) | Plan §9.1 트리거 조건 충족 시 착수 (YAGNI) |
| wiki-usage-attribution | 인용 강제 — 답변이 위키를 실제 반영했는지 검증 축 | 별도 PDCA (목차 id 병기가 선행 완료되어 착수 용이) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-23 | 완료 보고서 — Match 100%, 이터레이션 0 | 배상규 |
