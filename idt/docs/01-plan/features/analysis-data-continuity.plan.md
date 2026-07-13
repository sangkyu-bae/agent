# analysis-data-continuity Planning Document

> **Summary**: 멀티턴 대화에서 데이터분석 노드가 사용한 원천 데이터(검색/도구/엑셀 산출)를 세션 단위로 영속·복원하고, 보유 데이터로 부족한 후속 요청은 검색 워커/도구 재호출로 이어지게 하여 "이전 데이터 소실" 응답을 제거한다.
>
> **Project**: sangplusbot (idt 백엔드 중심)
> **Author**: 배상규
> **Date**: 2026-07-06
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 턴1에서 "나의 휴가데이터를 그래프로 그려줘"로 차트 생성에 성공해도, 턴2 "전체 사용자 그래프 그려줘"에서 "데이터를 제공해주시면 분석하겠다"는 응답이 나온다. 워커/도구가 수집한 원천 데이터가 턴 종료 시 어디에도 저장되지 않아(대화 히스토리는 user/assistant 텍스트만 영속) 후속 턴의 분석 노드가 데이터 없음 상태로 시작하기 때문이다. |
| **Solution** | ① 턴 종료 시 분석에 사용된 데이터 스냅샷을 assistant 메시지 부속(JSON)으로 영속(charts 선례와 동형) ② 다음 턴 컨텍스트 빌드 시 스냅샷을 검색결과 규약 메시지로 재주입해 분석 노드가 기존 코드 그대로 인식 ③ supervisor에 "보유 분석 데이터" 인지 블록을 추가해, 요청 범위가 보유 데이터를 벗어나면(예: 나→전체 사용자) 검색 워커를 재호출하도록 라우팅 개선. |
| **Function/UX Effect** | 후속 차트/분석 요청 시 "데이터를 제공해달라"는 회피성 응답 대신, 이전 데이터를 재사용해 즉시 그리거나(범위 내) 도구를 재호출해 새 데이터로 그린다(범위 밖). 커스텀 에이전트·General Chat 두 경로 모두 적용. |
| **Core Value** | 멀티턴 데이터 분석 대화의 연속성 확보 — 사용자가 같은 데이터를 반복 제공/재요청할 필요가 없어지고, 데이터 기반 후속 질문("이걸 월별로", "전체로 확대")이 자연스럽게 이어진다. |

---

## 1. Overview

### 1.1 Purpose

멀티턴 대화에서 **"직전 분석이 어떤 데이터를 들고 있었는지"를 세션 단위로 저장·복원**하는 구조를 만든다. 보유 데이터로 답할 수 있으면 재사용하고, 보유 범위를 벗어난 요청이면 데이터 재수집(검색 워커/도구 재호출)으로 라우팅한다.

### 1.2 Background — 원인 분석 (2026-07-06 코드 확인 결과)

**증상 재현 시나리오**
1. 턴1: "나의 휴가데이터를 그래프로 그려줘" → 차트 정상 생성
2. 턴2: "이제 전체 사용자 그래프 좀 그려줄래" → *"다른 사용자들의 휴가 데이터를 포함한 그래프를 직접 그릴 수는 없습니다. … 데이터를 제공해주시면 분석에 도움이 되겠습니다."*

**원인 1 — 워커 산출 데이터의 턴 간 비영속 (주원인, 구조적)**
- 커스텀 에이전트 경로: 검색 워커가 도구로 가져온 원천 데이터는 `AIMessage(name=worker, "[… 검색결과]\n…")` 형태로 **해당 런의 인메모리 state에만** 존재. 턴 종료 시 영속되는 것은 user 질문 + assistant 최종 답변 텍스트뿐 (`run_agent_use_case.py:833` `_save_assistant_message`). charts JSON은 저장되지만 "표시 전용 메타"로 컨텍스트 재투입 금지(D7-rev1, 캡션 1줄만 허용).
- 턴2 컨텍스트 복원(`run_agent_use_case.py:718` `_build_messages`)은 DB에서 `[user1, assistant1 텍스트, user2]`만 만든다. dict 메시지는 `is_search_result()`가 항상 False(`search_pipeline.py:44`)이므로 검색결과로 인식될 수 없다.
- 분석 노드(`workflow_compiler.py:834` `_analyze_context`)는 검색결과 메시지가 없으면 `"(별도 검색 결과 없음 — 전체 대화 문맥을 분석 대상으로 함)"` 분기로 빠지고, 이전 턴의 **답변 텍스트**(수치 요약 일부)만 보고 분석해야 한다.

**원인 2 — 분석 노드는 도구가 없어 스스로 데이터 수집 불가**
- 분석 노드는 의도적으로 도구 없이 생성된다(`workflow_compiler.py:216-222`). 데이터가 없으면 "제공해달라"는 응답 외 선택지가 없다.

**원인 3 — 후속 턴 라우팅이 데이터 재수집으로 이어지지 않음**
- 시각화 안내 블록(`supervisor_nodes.py:40` `_render_viz_guidance_block`)은 "차트는 분석 워커 경유 필수"를 강조한다. "외부 데이터가 필요하면 먼저 검색 워커로"라는 문구는 있으나, supervisor가 **현재 어떤 데이터를 보유 중인지** 알 방법이 없어 판단 근거가 없다. 후속 턴에서 분석 워커 직행 → 데이터 없음 응답으로 이어진다.

**원인 4 — 첨부(엑셀) 기반이면 후속 턴에 첨부 자체가 소실**
- `attachments`는 요청 단위(`build_initial_state`)라 턴2에는 빈 배열 → 엑셀 분기 비활성 → 문맥 분석 fallback.

**General Chat 경로도 동형 문제**
- ReAct 도구 결과(예: `internal_document_search` sources)는 영속되지 않고, `_persist_messages`(`use_case.py:543`)는 텍스트 답변 + charts(표시 전용)만 저장. 후속 턴은 차트 캡션 1줄(≤200자)만 보게 된다.

### 1.3 Related Documents

- `docs/rules/conversation-memory.md` — 요약 트리거·차트 메타 컨텍스트 규칙(D7-rev1). **본 기능은 이 규칙의 개정(스냅샷 채널 추가)을 수반한다** — D7→D7-rev1 개정과 동일한 문서화 절차로 진행.
- `docs/02-design/features/chart-context-continuity.design.md` — charts 부속 컬럼·캡션 정책 선례
- `src/application/agent_builder/search_pipeline.py` — 검색결과 메시지 규약(`format_search_result`/`is_search_result`) 단일 출처

### 1.4 사용자 결정 사항 (2026-07-06 확인)

| 질문 | 결정 |
|------|------|
| 발생 경로 | 커스텀 에이전트·General Chat **둘 다** — 본질은 "분석이 들고 있던 데이터를 멀티턴에서 저장하지 않는 것" |
| 턴1 데이터 출처 | 불명 / 둘 다 가능 — **도구 수집·엑셀 첨부 두 경우 모두 커버** |
| 기대 동작 | **둘 다** — 이전 데이터 보존·재사용 + 부족하면 도구 재호출로 새 데이터 수집 |
| 해결 범위 | **구조적 해결** — 세션 단위 영속·복원 구조 + 라우팅 개선, DB 스키마 변경 허용 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 분석 데이터 스냅샷 영속화**
- [ ] 스냅샷 스키마 정의(domain): 출처(worker/tool/excel), 원문 데이터(크기 상한 적용), 데이터 범위 설명(예: "사용자 본인 2026년 휴가 내역"), 생성 턴
- [ ] 저장 구조: `conversation_message`에 부속 JSON 컬럼(가칭 `analysis_data`) — charts 선례와 동형. (별도 테이블 대안은 Design에서 최종 확정)
- [ ] Flyway 마이그레이션 추가 (`db/migration/`) — FK 참조 시 CHARSET/COLLATE 명시 금지 관례 준수
- [ ] 커스텀 에이전트 경로: 턴 종료 시 해당 런의 검색결과 메시지들 + 엑셀 분석 산출 데이터를 스냅샷으로 저장
- [ ] General Chat 경로: 도구 결과(sources 등) 중 데이터성 산출을 스냅샷으로 저장

**B. 후속 턴 컨텍스트 복원**
- [ ] `RunAgentUseCase._build_messages`: 세션 최근 스냅샷을 `format_search_result` 규약 AIMessage로 재주입 → `_analyze_context`·`final_answer`가 **코드 수정 없이** 검색결과로 인식
- [ ] `GeneralChatUseCase` 컨텍스트 빌드: 스냅샷을 system 블록(예: `[이전 분석 데이터]`)으로 재주입
- [ ] 크기 상한·보존 개수(최근 N개) config화 (`src/config.py`, 하드코딩 금지)
- [ ] 요약(compact) 경로와의 공존 — 3대 설계 제약 (2026-07-06 판단 확정):
  1. **스냅샷 복원은 최근 윈도우가 아니라 세션 전체 히스토리에서 최신 N개 조회** — 요약 정책은 실제로 메시지 6개 초과 시 발동하고 최근 **메시지 3개**만 남기므로(`SummarizationPolicy`, `policies.py:41,86` — 문서의 "턴 6회"와 달리 메시지 개수 기준), 스냅샷 부착 메시지는 4번째 질문부터 이미 윈도우 밖. `_find_recent_charts`(전체 히스토리 역순 스캔) 선례와 동형으로 복원한다
  2. **스냅샷은 summarizer 입력에 절대 미포함 + 재주입 메시지는 비영속** — 컨텍스트 빌드 시점에만 생성하고 DB에 메시지로 저장하지 않아, 다음 compact의 요약 대상에 재유입되어 이중 비대해지는 루프를 차단한다
  3. **상한 산정 기준은 compact 후 총량** — "요약 + 최근 메시지 3개 + 스냅샷"이 한 턴의 컨텍스트가 되므로, 스냅샷 상한은 이 총량 기준으로 Design에서 수치 확정. 오래된 스냅샷 staleness는 보존 N개 + (필요 시) 턴 거리 컷오프로 완화

**C. 데이터 부족 시 재수집 라우팅**
- [ ] supervisor decision 프롬프트에 `[보유 분석 데이터]` 인지 블록 추가(스냅샷의 범위 설명 요약) — "요청이 보유 데이터 범위를 벗어나면 검색 워커로 먼저 데이터를 수집하라" 지침
- [ ] 분석 노드 프롬프트 개선: 데이터가 요청 범위에 부족하면 "제공해달라"가 아니라 **어떤 데이터가 부족한지 명시**하는 출력 규약 (quality_gate/supervisor 재라우팅 연계는 Design에서 확정)
- [ ] General Chat: system prompt에 보유 데이터 블록 추가 → ReAct가 도구 재호출 판단

**D. 규칙 문서·테스트**
- [ ] `docs/rules/conversation-memory.md`에 스냅샷 채널 규칙 개정 추가 (투입 위치·상한·요약 미포함)
- [ ] TDD: 스냅샷 저장/복원/상한/요약 공존/라우팅 블록 각각 테스트 선행 작성

### 2.2 Out of Scope

- 프론트엔드 변경 — 스냅샷은 LLM 컨텍스트 전용, UI 노출 없음 (이력 API 응답 스키마 불변)
- 차트 편집 경로(`ChartFollowupPolicy` EDIT → transformer) — 기존 동작 유지
- 스냅샷 데이터의 PII 마스킹 적용 — 기존 pii-masking 모듈 배선은 별도 후속(pii-masking-integration)에서 일괄 처리. 본 plan에서는 보존기간/크기 상한으로 위험 최소화만
- 벡터 DB 저장 — 금지 규칙 유지 (대화·데이터 원문은 MySQL만)
- Excel 첨부의 파일 자체 재사용(파일 보관 정책) — 산출 **데이터** 스냅샷만 저장, 원본 파일 재분석은 범위 외

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 커스텀 에이전트 턴 종료 시 검색/엑셀 산출 데이터를 스냅샷으로 영속 (크기 상한 초과분은 절단 + 표기) | High | Pending |
| FR-02 | General Chat 턴 종료 시 도구 산출 데이터성 결과를 스냅샷으로 영속 | High | Pending |
| FR-03 | 후속 턴 컨텍스트 빌드 시 최근 스냅샷을 검색결과 규약(agent)/system 블록(chat)으로 재주입 | High | Pending |
| FR-04 | 재주입 후 분석 노드가 "검색 결과 있음" 분기로 동작 — 이전 데이터 기반 후속 차트/분석 성공 | High | Pending |
| FR-05 | supervisor 프롬프트에 보유 데이터 인지 블록 — 범위 밖 요청 시 검색 워커 우선 라우팅 | High | Pending |
| FR-06 | 분석 노드: 데이터 부족 시 부족한 데이터 명시 출력 (회피성 "제공해달라" 응답 제거) | Medium | Pending |
| FR-07 | 스냅샷 크기 상한·보존 개수 config화 | Medium | Pending |
| FR-08 | 요약 발동 세션에서도 스냅샷 채널 유지, 요약 본문에는 미포함 | High | Pending |
| FR-09 | `conversation-memory.md` 규칙 개정 반영 (스냅샷 채널 조항) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 토큰 비용 | 스냅샷 재주입으로 인한 턴당 컨텍스트 증가 ≤ 상한(config, 초안 8k chars) | 상한 테스트 + LangSmith 트레이스 확인 |
| 하위 호환 | 스냅샷 없는 기존 세션은 현행과 동일 동작 (컬럼 NULL 허용) | 회귀 테스트 |
| 아키텍처 준수 | 스냅샷 스키마·상한 정책은 domain, 저장/복원 흐름은 application, 컬럼 매핑은 infrastructure | `/verify-architecture` |
| 테스트 | 신규 로직 테스트 선행 작성 (Red→Green) | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현 시나리오 통과: 턴1 "나의 휴가데이터 그래프" → 턴2 "전체 사용자 그래프" 시, (보유 데이터 범위 밖이므로) 검색 워커/도구 재호출이 발생하거나, 최소한 부족한 데이터를 명시한 응답 — "데이터를 제공해달라"식 문맥 소실 응답 없음
- [ ] 범위 내 후속 요청(예: "방금 데이터를 월별로 다시 그려줘") 시 도구 재호출 없이 스냅샷만으로 차트 생성
- [ ] 두 경로(커스텀 에이전트 / General Chat) 모두에서 위 시나리오 검증
- [ ] 요약 발동(6턴 초과) 후에도 스냅샷 기반 후속 분석 정상 동작
- [ ] 기존 pytest 통과 (사전 실패 건 제외 신규 회귀 0건) + Flyway 마이그레이션 적용 확인

### 4.2 Quality Criteria

- [ ] 스냅샷 저장·복원·상한·요약 공존 각각 단위 테스트 존재
- [ ] config 값 하드코딩 없음, logger 규칙(LOG-001) 준수
- [ ] `is_search_result` 규약 재사용으로 분석/최종답변 노드 무수정 (수정 최소화 검증)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 스냅샷 재주입으로 컨텍스트 토큰 비대 → 비용 증가·요약 정책 취지 훼손 | High | Medium | 크기 상한 + 최근 N개만 유지 + 요약 본문 미포함. Design에서 상한 수치를 실데이터로 검증 |
| "대화 메모리 정책 변경 금지" 조항과의 충돌 인식 | Medium | Medium | 기존 요약 트리거·최근 3턴 규칙은 **무변경**. 부속 채널 추가는 D7-rev1 선례처럼 규칙 문서 개정으로 정식화 (임의 변경 아님) |
| 휴가 데이터 등 개인정보가 스냅샷으로 장기 보존 | Medium | Medium | 세션 스코프 유지(기존 대화 저장과 동일 수명) + 상한 절단. 마스킹은 pii-masking-integration 후속에서 일괄 |
| supervisor가 보유 데이터 블록에도 불구하고 여전히 분석 직행 | Medium | Medium | 프롬프트 개선 + FR-06(부족 명시 출력)으로 2중 안전망. 필요 시 Design에서 강제 라우팅 훅(`AttachmentRoutingHooks` 동형) 검토 |
| 스냅샷 저장 실패가 본 답변 흐름을 막음 | Medium | Low | charts 선례처럼 graceful degradation — 저장 실패는 로깅 후 계속 |
| 요약본에는 "데이터를 분석했다"는 사실이 남는데 스냅샷은 보존 N개 초과로 축출된 경우 — LLM이 데이터 보유로 착각할 수 있음 | Medium | Low | 보유 데이터 인지 블록(FR-05)이 "현재 실제 보유 스냅샷"만 나열 → 없으면 재수집 라우팅. 분석 노드 부족-명시 규약(FR-06)이 2차 안전망 |
| General Chat의 "데이터성 도구 결과" 판별 모호 (검색 스니펫 vs 분석용 데이터) | Medium | Medium | Design에서 판별 기준 확정 (초안: 도구 화이트리스트 + 최소 구조 조건). 애매하면 저장하지 않는 보수적 기본값 |

---

## 6. Architecture Considerations

### 6.1 Project Level

기존 구조 유지 — 백엔드 Thin DDD (domain/application/infrastructure). 신규 레이어 없음.

### 6.2 Key Architectural Decisions (Design 단계에서 최종 확정)

| Decision | Options | 초안 선택 | Rationale |
|----------|---------|----------|-----------|
| 저장 위치 | ① `conversation_message` 부속 JSON 컬럼 ② 별도 테이블 | **① 부속 컬럼** | charts 선례와 동형, 마이그레이션 1개, 세션 조회 1회로 복원 가능. 스냅샷이 크거나 메시지와 수명이 다르면 ②로 전환 |
| agent 경로 재주입 형식 | ① `format_search_result` 규약 AIMessage ② system 블록 | **①** | `is_search_result` 규약을 재사용해 분석/최종답변 노드 무수정. "검색 결과 있음" 분기가 자연 동작 |
| 재수집 유도 방식 | ① supervisor 프롬프트 인지 블록 ② 강제 라우팅 훅 ③ 분석 노드에 도구 부여 | **① (+FR-06 안전망)** | 분석 노드 무도구 원칙(현 설계) 유지. ③은 아키텍처 변경이라 배제, ②는 ① 실패 시 Design에서 재검토 |
| 스냅샷 갱신 정책 | 턴마다 append / 최신 N개 유지 / 최신 1개 교체 | **최신 N개 유지 (config)** | 여러 데이터셋 병행 분석 대화 지원 + 비대 방지 |

### 6.3 영향 파일 목록 (초안)

```
백엔드 (idt/)
├── db/migration/V0xx__add_analysis_data_to_conversation_message.sql  [신규]
├── src/domain/conversation/entities.py                    [수정] ConversationMessage.analysis_data 부속
├── src/domain/conversation/ (신규 policy)                  [신규] 스냅샷 스키마·크기 상한·보존 정책
├── src/infrastructure/persistence/models/conversation.py  [수정] 컬럼 추가
├── src/infrastructure/persistence/mappers/conversation_mapper.py [수정]
├── src/application/agent_builder/run_agent_use_case.py    [수정] 저장(스냅샷 수집)·복원(_build_messages 재주입)
├── src/application/agent_builder/supervisor_nodes.py      [수정] 보유 데이터 인지 블록
├── src/application/agent_builder/workflow_compiler.py     [수정 최소화] 분석 노드 부족-명시 출력 규약(프롬프트)
├── src/application/general_chat/use_case.py               [수정] 저장·복원 동형 적용
├── src/config.py                                          [수정] 상한/보존 개수 설정
├── docs/rules/conversation-memory.md                      [개정] 스냅샷 채널 규칙
└── tests/ (agent_builder·general_chat·conversation)        [신규/수정]
```

---

## 7. Convention Prerequisites

- 백엔드 `idt/CLAUDE.md` 준수: 레이어 규칙, 함수 40줄, logger 필수, config 하드코딩 금지, Repository 내 commit 금지
- DB 세션 규칙(`docs/rules/db-session.md`): 한 UseCase 내 단일 세션
- 마이그레이션: Flyway `V0xx__` 네이밍, FK 참조 테이블에 CHARSET/COLLATE 명시 금지 (errno 3780 선례)
- 신규 환경변수: 없음 (config 기본값으로 처리)
- 프론트 API 계약: 응답 스키마 불변이므로 동기화 불필요 (변경 발생 시 `/api-cotract` 실행)

---

## 8. Next Steps

1. [ ] `/pdca design analysis-data-continuity` — 설계 문서 작성 (저장 위치·스냅샷 스키마·General Chat 데이터성 판별 기준·상한 수치 확정, 재수집 라우팅 실패 시 강제 훅 여부 결정)
2. [ ] 구현 (TDD: domain 정책 → 영속 계층 → agent 경로 저장/복원 → 라우팅 블록 → General Chat 동형 적용 순)
3. [ ] `/pdca analyze analysis-data-continuity` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-06 | Initial draft — 원인 분석(4개 요인) + 사용자 결정 4건 반영 | 배상규 |
| 0.2 | 2026-07-06 | 요약(compact) 정책과의 공존 판단 반영 — 3대 설계 제약(전체 히스토리 스캔 복원·요약 입력 미포함·compact 후 총량 기준 상한) + 메시지 개수 기준 발동 사실 명시 | 배상규 |
