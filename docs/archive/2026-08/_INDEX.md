# Archive Index — 2026-08

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| eval-hub | completed | 98% | 2026-08-03 | [eval-hub/](eval-hub/) |
| fix-agent-planner-hitl | completed | 100% | 2026-08-06 | [fix-agent-planner-hitl/](fix-agent-planner-hitl/) |
| agent-create-entry | completed | 96% | 2026-08-13 | [agent-create-entry/](agent-create-entry/) |
| intent-analyzer | completed (Partial) | 100% | 2026-08-13 | [intent-analyzer/](intent-analyzer/) |
| tool-recommender | completed | 97.38% | 2026-08-14 | [tool-recommender/](tool-recommender/) |
| intent-slot-elicitation | completed | 99% | 2026-08-17 | [intent-slot-elicitation/](intent-slot-elicitation/) |
| prompt-composer | completed | 97% | 2026-08-18 | [prompt-composer/](prompt-composer/) |
| agent-create-pipeline | completed | 97% | 2026-08-19 | [agent-create-pipeline/](agent-create-pipeline/) |
| agent-create-wizard | completed | 95% | 2026-08-20 | [agent-create-wizard/](agent-create-wizard/) |
| prompt-depth | completed | 99% | 2026-08-20 | [prompt-depth/](prompt-depth/) |
| wizard-chat-layout | completed | 98% | 2026-08-20 | [wizard-chat-layout/](wizard-chat-layout/) |

---

## 이월 항목 (Carry-over)

> 아카이브 시점에 미완이었던 항목. 후속 사이클 진입 전 확인할 것.

| Feature | 이월 항목 | 성격 | 진입 조건 |
|---------|----------|------|-----------|
| ~~**intent-analyzer**~~ | ~~**실 LLM 호출 검증 1회 (G1)**~~ → **✅ intent-slot-elicitation 사이클에서 해소.** 실측 결과 **프롬프트 이전에 스키마가 깨져 있었다** — 자유 키 `dict` 때문에 OpenAI structured outputs 가 400 을 반환해 판정이 **항상 `degraded`**, 즉 모듈은 출시 이후 실 LLM 에서 한 번도 동작한 적이 없었다. 위키 계약 2(과차단)는 실측 결과 **문제 없음** | — | **해소됨** (Analysis §10.1 / §10.5) |
| intent-analyzer | 배선 자체 — supervisor shadow 1단계 → 조언 주입 2단계 | 의도적 스코프 밖 (Plan D8) | G1 해소 완료 → **진입 가능** |
| intent-analyzer | 전체 스위트 기존 실패 58건 (parser 21 / agent_builder_stream 9 / retriever 7 / general_chat 7 …) | 본 기능 무관 — 라이브러리 버전 드리프트 | 독립 사이클 |
| **tool-recommender** | **Recall 100%는 후보 13개 기준** — Design §8.5 목표 규모(40+)에서의 Recall·지연 미검증. 도구가 많아질수록 오추천이 는다는 것이 Plan의 최초 문제의식인데, 정작 그 규모를 실측하지 못했다 | 환경 의존 (Naver Search MCP 복구 대기) | MCP 서버 확보 후 골드셋 풀 확장 재측정 |
| tool-recommender | MCP 저시그널 설명 보강(§3.3 name 토큰화) 효과 미측정 — 수집된 실 MCP 도구 4건 모두 완전한 docstring, stub 0건 | Plan 전제("MCP 설명은 stub")가 보편적이지 않았음 | stub 설명을 가진 MCP 등록 시 |
| tool-recommender | 커스텀 에이전트(`workflow_compiler`) 미배선 — General Chat 경로만 적용 | 의도적 스코프 밖 (module-4 한정) | 별도 사이클 |
| tool-recommender | `TOOL_SELECTOR_ENABLED=true`는 **로컬 `idt/.env`에만** 존재 (gitignore). 다른 환경은 코드 기본값 `False`로 꺼져 있다 | 배포 절차 | 스테이징/운영 적용 시 환경변수 주입 필요 |
| **intent-slot-elicitation** | **`AgentPlanner` 배선** — 이번 사이클 산출물(`AGENT_BUILD_SLOTS` 5축 프리셋)은 **소비자가 0인 죽은 코드**다. 배선하지 않으면 이 사이클의 가치가 0으로 남는다 | 의도적 스코프 밖 (Plan D8) | R2 실측 재평가 **✅ 충족** / compose 응답 계약 확정은 화면단 재작업 이후 |
| **intent-slot-elicitation** | **C3 과충전 부분 해소** — LLM 이 사용자가 말하지 않은 축까지 지어내 `missing=[]` → 되묻기 미발동. 프롬프트 강화로 3개 프로브 중 2개 정상화, 1개 잔존. **프롬프트로는 결정론적 보장 불가** | LLM 확률적 행동 | 배선 시 결정 필요 — ① 화면에서 "AI 가 이렇게 이해했어요" 확인 UI 로 흡수 ② optional 축은 사용자 확인 전까지 미확정으로 두는 Policy 규칙 도입 |
| intent-slot-elicitation | `suggestions` 공백 경향 — LLM 이 `questions[].options` 만 채우고 `suggestions` 를 생략. 질문 상한(3) **밖** 축의 선택지를 API 소비자가 볼 수 없다 | 기능 차단 아님 | 화면 작업에서 필요 여부 판단 |
| intent-slot-elicitation | 실 LLM 검증 표본 부족 — 프로브 3개 × 2회, `gpt-4o-mini` 단일. 확률적 실패율을 논할 표본이 아니며 모델 교체 시 재검증 필요 | 검증 깊이 | 배선 전 요청 유형 5~10개로 확대 |
| intent-slot-elicitation | 전체 스위트 기존 실패 58건 — intent-analyzer 이월과 **동일 건**. 두 사이클 연속 관측 | 본 기능 무관 | 독립 사이클 |
| ~~**prompt-composer**~~ | ~~**배선 자체 (N1)**~~ → **✅ agent-create-pipeline 사이클(08-19)에서 해소.** 파이프라인이 첫 소비자 — compose·세션 저장·bind 전부 배선. degraded 경고는 응답 `degraded_stages`로 노출 (화면 표시는 프론트 사이클로) | — | **해소됨** |
| **prompt-composer** | **R1 미해소 — `AgentComposer`와 프롬프트 생성 규칙 2벌 공존.** §10.3 대조표를 `prompts.py` 상단에 박아 "벌어지는지 볼 기준"은 만들었으나 통합/제거 판단(N5)은 미뤘다. 열어두면 두 규칙이 조용히 갈라진다 | 구조적 부채 | N1 배선 후 품질 비교 데이터 확보 시 |
| prompt-composer | **NFR-02 실측 초과 (G6)** — p95 목표 8초 대비 실 왕복 **10,026ms**. 표본 1개지만 도구 2개·이력 0턴이라는 **가장 가벼운 입력**이 넘겼다 | 목표치 재검토 | 배선 후 실측 표본 수집 → NFR 조정 또는 모델 재검토 |
| prompt-composer | FR-14 LangSmith 추적 미구현 (P2) | 추적할 트래픽이 아직 없음 | N1과 동시 |
| ~~prompt-composer~~ | ~~`intent` → `prompt-composer` 2단 호출 배선 (N2)~~ → **✅ agent-create-pipeline 사이클에서 해소.** 서버 소유 스펙(슬롯 4축)으로 파이프라인이 2단 호출을 내장 | — | **해소됨** |
| prompt-composer | 고아 세션(`agent_id=NULL`) TTL 정리 잡 (N4) | YAGNI 회피 | 실제 누적량 관측 후 |
| prompt-composer | 전체 스위트 기존 실패 58건 — **세 사이클 연속 동일 관측**. `parser` 21 / `agent_builder_stream` 9 / `retriever` 7 / `general_chat` 7 … | 본 기능 무관 — 라이브러리 버전 드리프트 | 독립 사이클 (3회 연속 이월 중) |
| **agent-create-pipeline** | **#15 생성 후 `GET /api/v1/agents/{id}` 일치 확인** — DoD 항목이나 실 DB·서버 필요 (Analysis §8.2) | 환경 의존 | 실서버 기동 시 E2E 체크리스트 최우선. `AGENT_PIPELINE_ENABLED=1` + `TOOL_SELECTOR_PROVIDER/MODEL` 필요 |
| ~~**agent-create-pipeline**~~ | ~~**프론트 배선**~~ → **✅ agent-create-wizard 사이클(08-20)에서 해소.** 4단계 위저드 + 5단계 진행바 + SSE 소비 + 되묻기 카드 전부 배선 | — | **해소됨** |
| **agent-create-pipeline** | **R1 수렴** — 도구선택+프롬프트 규칙이 이제 **3벌 공존** (AgentComposer / v3 auto / 파이프라인). Plan에 "검증 후 기존 경로 내부를 파이프라인 모듈로 교체 검토" 명문화 | 구조적 부채 (prompt-composer R1의 확장) | 파이프라인 실사용 품질 데이터 확보 시 |
| agent-create-pipeline | 멱등 키 — SSE 끊김 후 재호출 시 중복 생성 가능(R7). heartbeat로 완화했으나 근본 방어는 미도입 | YAGNI 회피 | 실사용에서 중복 생성 관측 시 |
| agent-create-pipeline | `AGENT_BUILD_SLOTS` 프리셋(intent-slot-elicitation 산출물)은 **여전히 소비자 0** — 파이프라인은 자체 스펙(`domain/agent_create_pipeline/spec.py`)을 사용. 두 슬롯 정의의 통합 여부 판단 필요 | 중복 정의 | 프론트 배선 시 compose 경로와 함께 검토 |
| agent-create-pipeline | 전체 스위트 기존 실패 58건 — **네 사이클 연속 동일 관측** | 본 기능 무관 | 독립 사이클 (4회 연속 이월 중) |
| **agent-create-wizard** | **실서버 수동 E2E 미실행 (SC-1·SC-2)** — 위저드 완주 → 스튜디오 저장 → `GET /api/v1/agents/{id}` 일치 확인. MSW 통합 테스트는 통과했으나 실 LLM·DB 경로는 미검증. pipeline 이월 #15와 동일 건 | 환경 의존 | 실서버 기동 시 E2E 체크리스트 최우선 (`AGENT_PIPELINE_ENABLED=1`, V061~V063 적용) |
| **agent-create-wizard** | **Act 1회차 수정분 미커밋** — 통합 테스트·컴포넌트 테스트 5종 신설, `agentCreateEntry.test.tsx` 삭제, 훅/페이지 수정이 `feature/agent-create-wizard` 워킹트리에만 존재 | 작업 절차 | 즉시 커밋 (보고서 §8.1) |
| agent-create-wizard | B-2 `stop_after="tools"` 정지 시 `unknown_tool_ids` 미검증 — 계약 명시 or 구현 보완 택1 | 계약 모호 | 다음 파이프라인 변경 시 |
| agent-create-wizard | Minor 잔여: B-3(저장 버전 clamp 이전 원본)·B-4/5(L1 테스트 2건)·F-9(MSW 기본 핸들러)·F-10(`llm_model_id` 핸드오프)·F-12(step① LoadingButton/글자수)·F-13(`MAX_CLARIFY_ROUNDS` 하드코딩) | 기능 차단 아님 | 위저드 후속 개선 시 일괄 |
| agent-create-wizard | Design 문서 drift 4건 (§3.5 intent 타입·§5.1 레이아웃·§11.1 파일명·§4.3 unknown_tool_ids) — 코드가 진실, 아카이브 문서는 미수정 | 문서 | `/wiki update` 시 반영 |
| agent-create-wizard | R1 수렴 미착수 — 규칙 3벌 공존 지속 (pipeline 이월 승계) | 구조적 부채 | 위저드 실사용 품질 데이터 확보 시 |
| agent-create-wizard | 전체 스위트 기존 실패 58건 — **다섯 사이클 연속 동일 관측** | 본 기능 무관 | 독립 사이클 (5회 연속 이월 중) |
| **prompt-depth** | **`PROMPT_COMPOSER_TIMEOUT_SEC` 상향 (20 → 30)** — 실측 prompt 단계 **14.5s / 상한 20s**, 여유 5.5s. 초과 시 degraded 폴백으로 떨어져 고정 문구 프롬프트가 저장된다 (Analysis G-02) | 설정 1줄 (`.env`) | **즉시** — 코드 변경 불필요, config 단일 출처 |
| **prompt-depth** | **짧은 옵션값이 프롬프트에서 희석 (G-05)** — 같은 `constraints` 축이라도 문장값(`"규정 원문에 없는 내용은 절대 답하지 않는다"`)은 거의 그대로 실리는 반면, **우리가 스펙에 넣어 버튼으로 제시하는 옵션값**(`"출처 명시 필수"`)은 `"정확하고 신뢰할 수 있는 정보를 제공"` 수준으로 번역된다. 사용자가 가장 쉽게 고르는 경로가 가장 약한 반영을 낳는다 | 프롬프트 지시 강도 | `prompts.py` 의 `constraints`/`decision_priority` 지침에 "주어진 문구를 그대로 한 줄로 싣는다" 추가 |
| prompt-depth | `style` 섹션이 얕다 (G-03) — 실측 3회 모두 한 줄이며 intent `tone` 값을 거의 복사 (`격식체` → `격식체`). Plan R-02가 예상한 "섹션이 늘면 일부를 얕게 쓴다"의 실제 발현 지점 | 프롬프트 지시 강도 | G-05와 같은 파일·같은 성격 — 일괄 조정 |
| prompt-depth | **Check 검증 잔여물** — dev 시드 계정 `testuser@sangplus.dev`, 검증용 에이전트 `842f0ea6-81ed-4cea-8359-34552e4fe579` (`[검증용] prompt-depth E2E`), prompt_session 5건이 개발 DB에 남음 | 정리 | 즉시 (`scripts/seed_test_users.sql` 하단 DELETE 구문 / 스튜디오에서 에이전트 삭제) |
| prompt-depth | Design 문서 drift 5건 — §5.1 폴백 상수에 `_FALLBACK_ROLES` 누락, §9.2 `MAX_CLARIFY_ROUNDS` 위치(`index.tsx` → `types/agentPipeline.ts`), §13 O-1/O-3 판정 미기입. **코드가 진실**, 아카이브 문서는 미수정 | 문서 | `/wiki update` 시 반영 |
| **prompt-depth** | **기존 실패 건수는 58이 아니라 80** — Plan QC-3에 58로 적혔으나 `git stash` 로 baseline 을 실측한 결과 **80건**. 다섯 사이클 연속 이월된 "58건"은 **미검증 수치가 복사된 것**이다. 실패 파일 10개(parser·retriever·es_client·ws_router·general_chat·main·agent_builder_stream·collection_router·run_agent_observability) 전부 본 기능과 커플링 0 | 기준값 오류 | 다음 사이클부터 **80** 을 기준으로 diff. 회귀 측정 전 `.pytest_cache` 삭제 필수 (잔재가 삭제된 옛 테스트 이름을 6건 되살려 오탐을 만든 사례 있음) |
| prompt-depth | **R1 수렴 — 이제 프롬프트 스키마가 두 벌** (파이프라인 7섹션 마크다운 vs `agent_composer`/v3 auto 4블록 대괄호). 이번 사이클이 Fix 탭을 두 번 "범위 밖"으로 미루면서 격차가 커졌다 | 구조적 부채 (3사이클 연속 승계) | **다음 사이클 1순위 후보.** 생성 경로 3종 통합 |
| prompt-depth | `schema_version=1` 행 1건 + 대괄호 프롬프트 에이전트들이 v2와 공존. 조회는 `assembled` 만 쓰므로 동작 영향 없음 | 표기 이원화 (사용자 수용 결정) | 재생성이 아니라 "사용자가 원할 때 업그레이드" 형태로 별도 사이클 |
| **wizard-chat-layout** | **트랜스크립트 `aria-live` 미적용 (I-2)** — 자동 스크롤의 포커스 탈취는 없으나 스크린리더가 신규 카드 도착을 알림받지 못함. Checkpoint 5에서 사용자 결정으로 이월 | 접근성 | 위저드 후속 개선 시 (코드 몇 줄) |
| wizard-chat-layout | Design 문서 표기 정정 (I-1/M-1) — §8.3/§11.1 테스트 배치(L3 상당수가 `index.test.tsx`에 구현), `scrollKey` 타입(`unknown`→`string`), 파일 목록 `index.test.tsx` 누락. **코드가 진실**, 아카이브 문서는 미수정 | 문서 | `/wiki update` 시 반영 |
| **wizard-chat-layout** | **구현 변경분 전체 미커밋** — WizardShell 신설, index.tsx 재조립, question-card `relative` 수정 등이 `feature/agent-create-wizard` 워킹트리에만 존재. 선행 기능(prompt-depth·agent-create-wizard) 잔여분과 혼재 → **분리 커밋 필요** (M-2) | 작업 절차 | 즉시 |
| wizard-chat-layout | `MAX_ASSEMBLED_CHARS=8000` / `MAX_CLARIFY_ROUNDS=3` 서버 미러 값 대조 (N-1) — 어긋나면 저장 422 또는 불필요한 차단. prompt-depth 잔여분 커밋 전 `idt/` 실제 값 확인 | 계약 검증 | 커밋 전 |
| wizard-chat-layout | 위키 후보: "sr-only(absolute)와 스크롤 컨테이너 클리핑 탈출" — 숨김 라디오가 positioned 조상 없이 body 기준 배치되면 overflow 클리핑을 탈출해 문서 스크롤바를 만든다. question-card 실사례 + 회귀 가드 테스트 존재 | 지식 자산 | `/wiki update` 시 등재 |
