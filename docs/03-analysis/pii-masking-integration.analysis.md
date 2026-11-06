# pii-masking-integration Gap Analysis

> **Project**: sangplusbot (idt 백엔드)
> **Date**: 2026-11-05
> **Phase**: Check
> **Plan**: v0.2 · **Design**: v0.5
> **대상**: worktree `wt/pii-masking`, 브랜치 `feature/pii-masking-integration` (미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 엔진은 있으나 배선이 없어 실효가 없다. 대화 경로의 PII가 외부 LLM으로 원문 전송된다. |
| **WHO** | P1(개인정보가 섞인 질문·문서를 다루는 사용자), P3(개인정보 처리를 통제해야 하는 관리자), P2(별도 설정 없이 보호받는 에이전트 소유자) |
| **RISK** | 미들웨어를 지나지 않는 경로의 누락, 숫자 오탐으로 인한 답변 품질 저하, 스트리밍 중 placeholder 노출 |
| **SUCCESS** | 대화 경로의 모든 외부 LLM 호출 입력에서 원본 PII 0건, 사용자 화면·DB에 placeholder 0건, 코퍼스 오탐 기준 충족, shadow→on 전환이 설정만으로 가능 |
| **SCOPE** | 포함: 엔진 보정, 미들웨어, 직접 호출 경로, 대화 경로 보조 LLM, 스트리밍 원복, MCP 검사, shadow 관측. 제외: 외부 도구 인자 마스킹, 임베딩 API, 이미지, 이름·주소 탐지, vault 영속화, 프론트 UI |

---

## 1. 결과 요약

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 93% | 구성요소 전부 존재. 감점: §8.4 `test_no_pii_in_logs` 없음, GuardedLlm 시그니처·DI 함수명이 Design과 다름, §11.1 파일 목록이 실제와 다름 |
| Functional | 85% | 스텁·TODO 없음. 감점: shadow 모드에서도 MCP 고아 차단이 동작(G-3), 계약 테스트가 팩토리 경유 우회를 못 잡음(G-1), FR-13 관측이 성공 경로에만 있음(G-2) |
| Contract (설정·DI·포트) | 92% | 설정 키·기본값·Literal 일치. raw/guarded 팩토리 분리는 계약 테스트로 고정. 감점: 추적 경고가 `enabled`를 보지 않음, 이름 드리프트 |
| **Overall (static, 0.2/0.4/0.4)** | **89.4%** | 0.2×93 + 0.4×85 + 0.4×92 |

런타임 근거는 별도로 기록한다. HTTP API 변경이 없어 bkit L1~L3 공식은 적용하지 않았다.

| 런타임 검증 | 결과 |
|------------|------|
| PII 관련 테스트 | 380 passed |
| 커버리지 (domain·application·infrastructure `pii_masking`) | 98% (558줄 중 12줄 미실행) |
| 전체 스위트 (module-4 후) | 59 failed / 11,250 passed. module-3 기준선과 FAILED 목록 동일, 새 실패 0 |
| on 모드 실런 (Design §8.6·§8.7) | 에이전트·일반 채팅 REST·WS 외부 요청 17건 원본 PII 0건, 토큰 574건 조각 0건 |
| verify-architecture·logging·tdd | 새 위반 0 (기존 위반 2종 유지) |

Critical gap은 없다. 확인한 코드 안에서 Design 범위의 외부 LLM으로 원본 PII가 나가는 경로는 찾지 못했다.

---

## 2. 전략 정합성

- **WHY 충족**: 대화 경로의 외부 LLM 요청에서 원본 PII가 빠진다(실런 17건). module-3에서 새던 근거 판정 LLM도 module-4에서 막혔다.
- **결정 준수**: D-01(카탈로그 미사용, 맨 앞 부착), D-02(Literal·타입 오타 실패), D-03(킬스위치 1개), D-04(FR-15 이월), D-05(OUTPUT_REDACT 제거), D-06(LangSmith 기동 경고), D-07(prompt guard 규칙 검사는 원본, 판정 LLM은 마스킹), D-08(구조화 출력 고아 보존), D-09(PiiGuardedLLMFactory, compiler는 raw)는 코드와 일치한다.
- **D-10 편차**: Design은 "모양 기반 고아 판정"을 정했지만, 미들웨어는 vault 기준 `has_orphan`, MCP 어댑터·집행기는 모양 기준 `PiiToolArgumentPolicy.find_orphan`을 쓴다. 그리고 MCP 쪽은 모드를 보지 않는다(G-3).

---

## 3. Plan FR 판정

| FR | 판정 | 근거 |
|----|:----:|------|
| FR-01 | ✅ | `middleware.py:43-89`, `message_masker.py:102-114` |
| FR-02 | ✅ | `request.override`만 사용(`middleware.py:59-66`). 상태·답변·DB는 원본 |
| FR-03 | ✅ | `workflow_compiler.py:1007-1015, 1044-1053`, `general_chat/use_case.py:491-493`, 계약 테스트 |
| FR-04 | ✅ | `main.py:926-934`(on은 raise, shadow는 경고), 메시지 단위 fail-closed `pii_masking_service.py:128-135` |
| FR-05 | ✅ | `_guard_llm`, `_guard_like`, 구조화 출력 재래핑 `guarded_llm.py:59-60` |
| FR-06 | ✅ | UtilityLLMProvider 2곳, 요약기, 대화 LLM, 차트, 도구 선별기. `RAGAgentUseCase`(`main.py:1535`)는 프론트가 호출하지 않는 독립 API(`/api/v1/rag-agent`)라 대화 경로 밖이지만 허용 목록에 사유가 없음(G-1) |
| FR-07 | ⚠️ | 직접 생성·create_agent 지점은 검사. `llm_factory=_llm_factory` 주입 후 `create()` 호출하는 우회는 검출하지 못함(G-1) |
| FR-08 | ✅ | `run_agent_use_case.py:411-417`, 서브에이전트 scope 전달 `workflow_compiler.py:1426` |
| FR-09 | ✅ | 두 경로 토큰 원복·flush, 실런 574건 조각 0 |
| FR-10 | ⚠️ | 인자·결과 타입별 건수 기록은 충족. 다만 shadow 모드에서도 인자를 차단해 "값을 바꾸지 않는다"를 어김(G-3) |
| FR-11 | ✅ | MCPToolLoader 전 지점, McpActionExecutor 주입. 파이프라인 `tool.ainvoke`는 `MCPToolAdapter._arun`을 거침 |
| FR-12 | ⚠️ | off=`enabled=false`, shadow는 LLM 요청 불변. 그러나 shadow에서 MCP 고아 차단이 동작(G-3) |
| FR-13 | ⚠️ | 에이전트 런 성공 경로만 `_record_pii_step`(`run_agent_use_case.py:431`). 예외·재귀 한도·승인 재개 경로에는 없음(G-2) |
| FR-14 | ✅ | 코퍼스 3종 + `test_corpus.py`, 허용 오탐 7건 `known_fp.txt` |
| FR-15 | ⏸ | 이월 (D-04) |
| FR-16 | ✅ | `message_masker.py:26-40` |
| FR-17 | ✅ | 기동 경고 `main.py:965-967` (G-6 경미 결함) |

## 4. Success Criteria 판정

| 기준 | 판정 | 근거 |
|------|:----:|------|
| FR-01~17 구현·테스트 통과 | ⚠️ | 380 통과. FR-07·10·12·13 부분 |
| 실런: 에이전트(react 워커, MCP 파이프라인, 승인 재개) + 일반 채팅 REST·WS | ⚠️ | 에이전트·일반 채팅 REST·WS 완료. **승인 재개 실런 없음** |
| 외부 요청 원본 PII 0, 답변·DB placeholder 0, 도구는 원본 인자 | ✅ | §8.7. 실제 PII가 든 MCP 결과는 서버가 사전 마스킹해 미검증(알려진 한계) |
| 스모크: 이메일 → 메일 도구 승인 화면·집행 인자 원본 | ❌ | 실행 기록 없음 |
| 스트리밍 실런 조각 0 | ✅ | 574건 |
| shadow→on 설정·재기동만으로 전환 | ✅ | `config.py:303` |
| `.env.example` 갱신 | ❌ | bkit 정책으로 세션 편집 불가. 수기 반영 대기 |
| 커버리지 80% 이상 | ✅ | 98% |
| 회귀 0 (FAILED diff) | ✅ | module-3 기준선과 동일 |
| verify 3종 통과 | ✅ | 새 위반 0 |
| 함수 40줄·중첩 2단계 | ⚠️ | 새로 40줄을 넘긴 함수 3개: `mcp_executor.execute` 33→46, `tool_adapter._arun` 37→50, `main._build_run_agent_uc` 39→43. 나머지 초과 함수는 원래 초과 |
| compile된 그래프 실행 테스트 | ✅ | `test_pii_masking_compile.py`, `_scripted_model.py` |

---

## 5. Gap 목록

### Critical

없음.

### Important

**G-3. shadow 모드(기본값)에서도 MCP 인자의 placeholder 모양 문자열을 차단한다.** (신뢰도 90%, 직접 확인)
- 근거: `get_pii_inspector()`는 masker가 있으면 모드와 무관하게 검사기를 돌려준다(`main.py:954-957`). `MCPToolAdapter._arun`(`tool_adapter.py:116-123`)과 `McpActionExecutor`(`mcp_executor.py:123-124`)는 검사기가 있으면 `PiiToolArgumentPolicy.find_orphan`으로 모양만 보고 차단한다.
- 실패 시나리오: 기본 설정(enabled=true, mode=shadow)으로 배포한 직후, 사용자가 "제목을 `[EMAIL_1] 회신 요청`으로 해서 메일 보내줘"라고 하면 MCP 호출이 `PII_ORPHAN_TOOL_ARG_NOTICE`로 막힌다. shadow 모드에서는 LLM이 placeholder를 받은 적이 없어 지어낼 이유도 없으므로, 차단은 순수한 부작용이다. FR-12의 "shadow는 탐지·기록만 한다"에 어긋난다.
- 수정 방향: 고아 차단은 on 모드에서만 하도록 한다(검사기 포트에 차단 여부를 노출하거나 어댑터에 모드를 함께 주입). 미들웨어(vault 기준)와 판정 규칙이 다른 점은 Design D-10에 기록한다.

**G-1. FR-07 계약 테스트가 팩토리 경유 우회를 검출하지 못한다.** (신뢰도 90%)
- 근거: `test_boundary_contract.py:109-116`은 `ChatOpenAI(` 등 직접 생성만 센다. `main.py`에서 raw `_llm_factory`를 받는 소비자(`RAGAgentUseCase` `:1535`, `AgentSpecInferenceService`, `SlotExtractor`, section_summary 등)는 검사 대상이 아니다.
- 실패 시나리오: 이후 대화 경로 use case가 `llm_factory=_llm_factory`를 받아 `create().ainvoke()`를 호출해도 모든 계약 테스트가 통과한다. 현재 소비자는 대화 경로 밖(독립 API·에이전트 생성 보조)이라 지금 새는 경로는 아니다.
- 수정 방향: `main.py`의 `llm_factory=_llm_factory` 키워드 인자를 사유와 함께 허용 목록으로 고정하는 계약 테스트를 추가한다.

**G-2. FR-13 관측이 에이전트 성공 경로에만 남는다.** (신뢰도 85%)
- 근거: `_record_pii_step`은 `run_agent_use_case.py:431`에서만 호출된다. GraphRecursionError 강등 경로, 예외 경로, 승인 재개(`_resume_graph`)에는 없다. 일반 채팅은 ai_run 스텝을 남기지 않는다.
- 실패 시나리오: 운영자가 shadow 집계로 on 전환을 판단할 때, 실패·한도 초과 런과 승인 재개 런의 탐지 건수가 빠져 집계가 작게 나온다.
- 수정 방향: 예외·강등·재개 경로에도 기록하거나, FR-13 범위를 "에이전트 런 정상 종료"로 Design에서 좁힌다. 일반 채팅은 로그 집계로 대체한다고 명시한다.

**G-11. Success Criteria 실런 2건 미실시.** (신뢰도 95%)
- 승인 재개 경로 on 모드 실런, 메일 도구 승인 스모크(승인 화면·`tool_args`·집행 인자 원본 확인)가 없다. 그래프 테스트로 승인 게이트 앞 원복은 검증했지만 실제 재개 흐름은 확인하지 않았다.

### Minor

| ID | 내용 | 신뢰도 |
|----|------|:------:|
| G-4 | Design 드리프트: §4.4 GuardedLlm `new_scope` 인자(실제는 `masker.new_scope()`), §10.2 `get_pii_masking()`(실제 `get_pii_masker`), §11.1 파일 목록(`utility_llm_provider.py` 수정 → D-09로 팩토리 방식, `tool_factory.py` → 실제 `tool_registry`·`mcp_tool_loader`). `PiiMaskingConfig` docstring의 "(module-3)" 잔재 | 95% |
| G-5 | `reserve_literals`가 이미 vault에 있는 키는 건너뛰어, 런 안에서 `[PHONE_1]`이 실제 번호에 배정된 뒤 사용자가 같은 문자열을 직접 치면 응답에서 실제 번호로 원복된다 | 70% |
| G-6 | `_pii_tracing_conflict`(`main.py:965-967`)가 `pii_masking_enabled`를 보지 않아 마스킹을 끈 상태에서도 경고한다 | 95% |
| G-7 | 에이전트 supervisor STEP_REASONING은 구조화 출력이라 고아를 보존해 화면에 `[EMAIL_9]` 같은 고아가 그대로 나갈 수 있다. 일반 채팅 추론은 redact되어 두 경로가 다르다 | 60% |
| G-8 | shadow에서 `PII_MASKING_TYPES` 오타는 경고 후 masker=None이 되어 관측·검사가 함께 꺼진다. Design §6.2 문구대로이지만 기본 모드에서 조용히 관측이 사라진다 | 85% |
| G-10 | 성능 NFR(호출당 20ms 미만) 벤치 없음. module-1에서 탐지기 50KB 14ms 실측만 있음 | 80% |
| G-12 | 새로 40줄을 넘긴 함수 3개(§4) | 100% |
| — | §8.4 `test_no_pii_in_logs` 미작성. 로그에는 타입별 건수만 남기도록 구현했고 verify-logging은 통과 | 80% |

---

## 6. 권장 조치

1. **G-3** (필수): MCP 고아 차단을 on 모드로 한정. 어댑터·집행기 테스트에 shadow 케이스 추가.
2. **G-1**: `llm_factory=_llm_factory` 주입 허용 목록 계약 테스트 추가.
3. **G-2**: 예외·강등·재개 경로 관측 추가 또는 Design 범위 축소.
4. **G-11**: 승인 재개·메일 승인 스모크 실런(Report 전).
5. **G-12, G-6, G-4**: 함수 분리, 경고 조건 수정, Design 문서 동기화.

---

## 7. Act-1 결과 (2026-11-05)

사용자 결정: "지금 모두 수정".

| Gap | 조치 | 근거 |
|-----|------|------|
| G-3 | `PiiInspectPort.find_orphan_argument` 추가. 서비스가 모드를 보고 판정(shadow는 항상 None). 어댑터·집행기는 판정을 위임 | `pii_masking_service.py` `find_orphan_argument`, `tool_adapter.py` `_pii_orphan_blocked`, `mcp_executor.py` `_has_pii_orphan`. 테스트: `TestFindOrphanArgument` 3건, 어댑터·집행기 shadow 케이스 각 1건 |
| G-1 | `ALLOWED_RAW_FACTORY_CONSUMERS` 9곳을 사유와 함께 고정, 변이 테스트 | `test_boundary_contract.py` `test_raw_llm_factory_consumers_match_allowlist`, `test_raw_factory_check_detects_new_consumer` |
| G-2 | 요약 로그를 `finally`로 이동(에이전트·일반 채팅), 승인 재개는 자체 scope 생성·전달 후 요약. ai_run 스텝은 정상 종료만(D-12) | `TestSummaryLog` 5건, 일반 채팅 2건 |
| G-6 | 추적 경고에 `pii_masking_enabled` 조건 추가 | `test_tracing_with_masking_disabled_does_not_warn` |
| G-12 | `execute` 46→35, `_arun` 50→36, `_build_run_agent_uc` 43→33 | 함수 길이 재측정 |
| G-4 | Design v0.6: §4.4 시그니처, §4.6 포트, §10.2 함수명, §11.1 파일 목록. docstring "(module-3)" 제거 | Design Version History |
| G-11 | 승인 스모크 실런(§8.8 of Design). **실행 중 새 결함 G-13 발견** | 아래 |

### G-13 (Act-1 중 발견, Critical → 해소)

- **현상**: on 모드에서 승인 필요 도구(`send_mail`)가 호출되지 않았다. action 파이프라인의 인자 작성 프롬프트는 "실제로 확인된 값만 사용, 예시 주소를 지어내지 않는다"를 요구하는데, LLM이 `[EMAIL_1]`을 미확인 값으로 보고 `grounded=false`를 반환했다. 답변에는 괄호 없는 `EMAIL_1`이 노출됐다. 메일·답변 등록 같은 승인 흐름이 on 모드에서 전부 멈추는 결함이다. 기존 실런은 조회 도구만 써서 드러나지 않았다.
- **조치 (D-11)**: placeholder가 실제로 나간 요청에만 system 끝에 `PII_PLACEHOLDER_NOTICE`를 붙인다. `PiiMessageMasker.mask_request`를 미들웨어·GuardedLlm이 함께 쓴다. 안내에는 번호 있는 예시를 넣지 않는다.
- **테스트**: `TestPlaceholderNotice` 6건, GuardedLlm 3건, 미들웨어 2건.
- **재실런**: 승인 대기 1건 생성, 승인 초안 `tool_args.to`와 집행 인자 `to` 모두 원본, 외부 요청 13건(런 8 + 재개 5) 원본 PII 0건. 실제 메일은 보내지 않았다(`call_tool` 가로채기).
- **범위 밖**: 초안 본문이 요청 문구와 다르게 생성되는 현상은 shadow에서도 같아 이 기능과 무관(action 초안 생성기 기존 동작).
- **회귀 실런**: D-11이 모든 on 요청을 바꾸므로 module-4의 4경로 실런을 다시 했다. 에이전트 REST·WS, 일반 채팅 REST·WS 외부 요청 18건 원본 PII 0건, 토큰 345건 조각 0건, `[REDACTED_]` 0건. 답변은 원본 연락처로 원복됐다.

### 재측정

| 축 | v0.1 | Act-1 |
|----|:----:|:-----:|
| Structural | 93% | 96% (§8.4 `test_no_pii_in_logs` 미작성만 남음) |
| Functional | 85% | 95% (G-1·2·3·13 해소. G-5·7·8 Minor 잔존) |
| Contract | 92% | 97% (G-4·6 해소) |
| **Overall (static)** | **89.4%** | **95.8%** |

전체 스위트(Act-1 후): 60 failed / 11,275 passed. module-4 기준선 대비 추가 1건 `test_html_font_embedder.py::test_embed_overhead_within_budget`은 실런과 동시 실행된 시간 예산 테스트로, 단독 3회 재실행 모두 통과했고 이 기능이 건드리지 않은 모듈이다. 새 회귀 0건.

Success Criteria 변경: 승인 재개 실런 ⚠️→✅, 메일 승인 스모크 ❌→✅(발송 가로채기), 함수 40줄 ⚠️→✅(신규 초과 0, `mcp_executor._call`은 기존 초과 47→49). `.env.example`은 여전히 수기 반영 대기.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | 최초 분석. static 89.4%, Critical 0, Important 4 | 배상규 |
| 0.2 | 2026-11-05 | Act-1: G-1·2·3·4·6·11·12 해소, 실런 중 발견한 G-13(on 모드 승인 흐름 중단) 해소. static 95.8% | 배상규 |
