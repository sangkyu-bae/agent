# claude-agent-e2e-fixes Planning Document

> **Summary**: 2026-11-19 실 E2E(Claude 에이전트로 여신 엑셀 보고서 생성)에서 드러난 결함 5건을 한 사이클로 고친다 — 퍼센트 문자열 집계, Anthropic 출력 한도, 최신 Claude 구조화 출력 400, 수퍼바이저 반복 루프, Claude 비용 추적.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 관리자 화면)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 단위 테스트는 모두 통과했지만 실 E2E에서 최신 Claude(Opus 5.5) 에이전트가 동작하지 않았다. 수퍼바이저 라우팅이 400(강제 tool_choice 거부)으로 실패하고, 출력 한도 4096을 thinking이 다 써서 분석 답이 비었다. Sonnet 4.6에서는 분석 워커를 13회 반복 호출하는 루프가 생겼고, 엑셀의 평균 금리(`"8.9%"` 문자열)는 빈칸이었으며, Claude 호출 비용은 모델명 `unknown`·토큰 0으로 기록됐다. |
| **Solution** | ① 연산 실행기가 퍼센트 문자열을 비율로 읽고, 전부 빈 집계 컬럼은 요약에 경고한다. ② `llm_model.max_output_tokens` 컬럼(V092)과 관리자 입력을 추가하고, `LLMFactory`가 Anthropic에 출력 한도(미설정 시 16000)와 요청 타임아웃을 넘긴다. ③ 강제 tool 호출을 거부하는 모델은 `LLMFactory`가 만든 모델의 `with_structured_output` 기본 방식을 `json_schema`로 바꾼다. ④ 같은 워커 연속 호출 상한을 넘으면 수퍼바이저에 제외 안내를 넣고, 그래도 고르면 최종 답변으로 끝낸다. ⑤ 사용량 콜백이 스트리밍 응답에서도 모델명·토큰을 읽는다. |
| **Function/UX Effect** | 관리자가 Opus 5.5를 등록하면 에이전트가 라우팅·분석·엑셀 생성까지 끝까지 동작한다. 엑셀 집계에 퍼센트 값이 들어가고, 빈 값이면 답변이 그 사실을 말한다. 진척 없는 반복이 최대 수 회로 끝나 비용 폭주가 사라진다. 사용량 화면의 Claude 비용이 실제 토큰 기준으로 집계된다. |
| **Core Value** | 관리자가 고른 모델이 실제로 동작하는 것이 모델 레지스트리의 전제다. 최신 Claude를 등록할 수 있게 하고, 실패가 조용히 빈 결과·무한 반복·0원 비용으로 감춰지지 않게 한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 실 E2E에서 최신 Claude 에이전트가 라우팅 400·빈 답·반복 루프로 동작하지 않았고, 엑셀 집계 빈칸과 비용 추적 0이 조용히 감춰졌다 |
| **WHO** | P2(에이전트 소유자) — 관리자가 등록한 모델로 에이전트를 만들고 결과물(엑셀 등)을 받는 사용자, 그리고 사용량·비용을 보는 관리자 |
| **RISK** | json_schema 전환 시 Anthropic 스키마 제약 위반(41개 호출 지점), 큰 출력 한도의 SDK 비스트리밍 거부, 연속 호출 상한이 정상 재호출을 막음, V092 운영 적용 순서 |
| **SUCCESS** | 같은 E2E 시나리오(Opus 5.5, data_analysis + excel_export)가 끝까지 성공하고 엑셀 값이 원천 직접 계산과 일치, 평균 금리 채워짐, 반복 호출이 상한에서 멈춤, ai_llm_call에 모델명·입출력 토큰 기록 |
| **SCOPE** | 5개 모듈: M1 퍼센트·빈 컬럼 / M2 출력 한도(DB·API·관리자 화면·팩토리) / M3 구조화 출력 / M4 반복 루프 / M5 비용 추적. PR 1개 |

---

## 1. Overview

### 1.1 Purpose

관리자가 등록한 최신 Claude 모델로 만든 에이전트가 실제로 끝까지 동작하게 하고, 실 E2E에서 드러난 데이터·비용 정확도 결함을 고친다.

### 1.2 Background

2026-11-19 인프로세스 실 E2E(실 DB·실 LLM)로 "여신 현황 엑셀(600행) → 팀장 보고용 엑셀 3시트" 요청을 돌렸다. 재현 자산과 측정값은 메모리 `claude-latest-compat-e2e-findings` 참고.

| 실행 | 결과 | 드러난 결함 |
|------|------|------------|
| Opus 5.5, data_analysis + excel_export | 45초 만에 실패 응답, 엑셀 없음 | ② 분석 LLM 출력 4096 전부 reasoning, text 0자(`stop_reason=max_tokens`) → 환각 검사 ValueError · ③ 수퍼바이저·검색 판단 `tool_choice: type "tool" and "any" are not supported for this model` 400 |
| Sonnet 4.6, data_analysis + excel_export | 15분+ 진행 중 수동 중단, 엑셀 없음 | ④ 분석 LLM이 600행을 직접 세며 69명→43·46명으로 틀림, 수퍼바이저가 "수치 불일치"로 분석만 4회 재호출(LLM 분석 13회, 약 $2) |
| Sonnet 4.6, excel_export 단독 | 27초 성공, 69행·합계·정렬·서식 정확 | ① 평균 금리 빈칸(`"8.9%"` 미해석), 답변은 "% 형식 적용"이라고 말함 |
| 세 실행 공통 | — | ⑤ ai_llm_call `model_name=unknown`, prompt/completion 0, total만 기록 |

원인 조사 결과(2026-11-19):

- ② langchain-anthropic 1.6.1은 `claude-opus-5-5`를 모르는 모델로 보고 `max_tokens` 기본값을 4096으로 둔다(sonnet-4-6은 128000). `LLMFactory._create_anthropic`는 출력 한도를 넘기지 않는다. DB `llm_model.max_tokens`는 **컨텍스트 크기**(sonnet-4-6=200000)라 출력 한도로 쓸 수 없다.
- ③ `with_structured_output`이 30개 파일 41곳에서 쓰인다. 기본 `method="function_calling"`은 Anthropic에 `tool_choice: tool`을 보낸다. Claude API 기준으로 Opus 5.5·Sonnet 5.5·Fable 5.1/5.2·Mythos 5.1/5.2는 이를 400으로 거부한다. langchain-anthropic 1.6.1은 `method="json_schema"`를 지원한다.
- ④ 수퍼바이저에 같은 워커 반복을 막는 장치가 없다(에이전트 순환 검사 `validate_no_cycle`만 있음). 반복 한도(`max_iterations`, 기본 25)까지 계속된다.
- ⑤ 수퍼바이저 등은 스트리밍(`_astream`)으로 호출된다. 이때 `LLMResult.llm_output`이 비어 `UsageCallback._extract_model`이 `unknown`을 내고, provider도 `unknown`이라 토큰을 OpenAI 키(`prompt_tokens`)로 읽어 0이 된다. 실측(합계만 기록)과 일치하는 **추정 원인** — Design에서 확인.
- ① `spec_policies.clean_numeric_text`가 `%`를 처리하지 않는다. `coerce_cell(percent)`만 `%`를 다룬다.

### 1.3 Related Documents

- 선행: `idt/docs/archive/2026-11/excel-generator-spec-ops/` (ops·column_types), PR #118(Claude 호환 1차: temperature·블록 리스트), PR #120(엑셀 분석 유틸리티 LLM 주입)
- 위키: `docs/wiki/backend/patterns/structured-output-strict-schema.md`(strict 스키마 자유 키 dict 금지), `llm-output-trust-boundary.md`, `supervisor-graph-contracts.md`
- 메모리: `claude-latest-compat-e2e-findings`, `idt-local-db-and-run-repro`

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 퍼센트·빈 컬럼** — ops 실행기의 숫자 해석이 `"8.9%"`를 0.089로 읽음(filter 값 `"5%"`도 0.05). 집계 결과가 전부 빈 컬럼이면 생성 결과 요약에 경고
- [ ] **M2 출력 한도** — `llm_model.max_output_tokens`(V092, NULL 허용) · 엔티티·리포지토리·API 스키마·프론트 타입·관리자 모델 화면 입력 · `LLMFactory`가 값이 있으면 전달, Anthropic은 NULL이면 설정 기본값 16000 · Anthropic에 요청 타임아웃 명시(큰 값도 SDK가 거부하지 않게) · 저장 시 범위 검증
- [ ] **M3 구조화 출력** — domain 정책 "강제 tool 호출 지원 여부" · 해당 모델은 `LLMFactory`가 만든 모델의 `with_structured_output` 기본 방식을 `json_schema`로 · PII 프록시 경유 동작 확인 · LLM이 보는 스키마의 Anthropic 제약 위반 정적 검사
- [ ] **M4 반복 루프** — 같은 워커 연속 호출 상한(설정, 기본 2) · 상한 도달 시 수퍼바이저 프롬프트에 제외 안내 · 그래도 같은 워커를 고르면 최종 답변으로 종료(사유 기록)
- [ ] **M5 비용 추적** — 사용량 콜백이 스트리밍 응답에서도 모델명(응답 메시지 메타데이터·invocation params)과 provider를 얻음 · 토큰 정규화를 provider가 아닌 키 존재로 판정
- [ ] 같은 E2E 시나리오를 Opus 5.5로 재실행해 완료 확인(재현 스크립트 커밋 여부는 Design에서 결정)

### 2.2 Out of Scope

- 분석 노드(data_analysis)가 원천 600행을 LLM 프롬프트에 통째로 넣는 구조 — 정확도·비용 문제지만 설계 변경이 크다(후속 후보)
- `max_iterations` 기본값·토큰 예산 정책 변경
- 과거 ai_llm_call 행의 모델명·토큰 보정(backfill)
- OpenAI·Ollama의 구조화 출력 방식 변경, Anthropic 구형 모델(4.6 이하)의 방식 변경
- `max_tokens`(컨텍스트) 컬럼의 의미·이름 변경
- 근거 판정 모델(`grounding_judge_model`) 기본값 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Module | Priority | Status |
|----|-------------|:------:|----------|--------|
| FR-01 | 숫자 해석(`clean_numeric_text` 계열)이 `%` 접미 문자열을 100으로 나눈 비율로 읽는다. 크기 비교·정렬·집계 모두 적용. `coerce_cell(percent)`와 같은 결과 | M1 | High | Pending |
| FR-02 | ops 결과에서 행이 1개 이상인데 값이 전부 빈 컬럼을 찾아 `ExcelGenerateResult`에 담고, 노드 요약 메시지에 "계산할 수 없어 비어 있음" 경고로 표시 | M1 | Medium | Pending |
| FR-03 | `llm_model.max_output_tokens INT NULL` 컬럼 추가(V092, 전 컬럼 COMMENT) + SQLAlchemy 모델 `comment=` | M2 | High | Pending |
| FR-04 | 엔티티·리포지토리·생성/수정 API 스키마·응답에 `max_output_tokens` 추가(additive). 1 이상 128000 이하 검증 | M2 | High | Pending |
| FR-05 | 프론트 `types/llmModel.ts`·서비스·관리자 모델 화면에 "최대 출력 토큰" 입력 추가(비우면 기본값 안내). 기존 `max_tokens`는 "컨텍스트 크기"로 라벨 명확화 | M2 | Medium | Pending |
| FR-06 | `LLMFactory`: 값이 있으면 provider별 출력 한도 인자로 전달. Anthropic은 NULL이면 `settings.anthropic_default_max_output_tokens`(16000) | M2 | High | Pending |
| FR-07 | ~~Anthropic 요청 타임아웃 명시~~ → Design §1.3: 삭제 (실호출에서 max_tokens 64000·128000이 타임아웃 없이 정상, SDK 거부 없음) | M2 | — | Dropped |
| FR-08 | domain 정책 `anthropic_supports_forced_tool_choice(model_name)` — 거부 모델 목록 + 이름 형식을 모르는 신형은 거부로 간주 | M3 | High | Pending |
| FR-09 | 거부 모델이면 `LLMFactory`가 만든 Anthropic 모델의 `with_structured_output` 기본 `method`를 `json_schema`로(호출부가 method를 명시하면 존중). 호출 지점 41곳 무수정 | M3 | High | Pending |
| FR-10 | `PiiGuardedLLMFactory` 프록시를 거쳐도 FR-09가 적용된다 | M3 | High | Pending |
| FR-11 | LLM이 보는 구조화 출력 스키마가 Anthropic 구조화 출력 제약을 위반하지 않음을 정적 테스트로 확인(위반 시 스키마 수정 또는 Design에서 예외 처리) | M3 | High | Pending |
| FR-12 | 같은 워커 연속 호출 횟수를 상태로 추적. 상한(`settings`, 기본 2) 도달 시 다음 수퍼바이저 프롬프트에 "방금 연속 수행됨 — 결과를 쓰거나 다른 단계로" 안내 | M4 | High | Pending |
| FR-13 | 상한 도달 후에도 같은 워커를 고르면 라우팅하지 않고 최종 답변으로 종료. 종료 사유를 기록(로그·런 단계) | M4 | High | Pending |
| FR-14 | 사용량 콜백: 모델명을 `llm_output` → 생성 메시지 `response_metadata`(`model_name`/`model`) → invocation params(`model`/`model_name`) 순으로 얻는다 | M5 | High | Pending |
| FR-15 | 토큰 정규화: provider와 무관하게 키 존재로 판정(`input_tokens`/`output_tokens` 또는 `prompt_tokens`/`completion_tokens`) | M5 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | OpenAI·Ollama·Anthropic 구형 모델(4.6 이하)의 요청 payload 무변경 (출력 한도 미설정 시) | 팩토리 payload 단위 테스트 |
| 회귀 | 기존 `with_structured_output` 호출 지점 41곳 무수정, 관련 테스트 무회귀 | pytest 영향 범위 + 계약 테스트 |
| 비용 | 진척 없는 워커 반복이 상한(기본 2) + 1회 안에서 멈춘다 | 실 E2E·단위 테스트 |
| 아키텍처 | 모델별 정책은 domain 순수 함수, 외부 의존 없음 | `verify-architecture` |
| DB | V092 전 컬럼 COMMENT, `tests/db/test_migration_ddl_comments.py` 통과 | pytest |
| 프론트 | 관리자 화면 입력·표시 테스트, tsc·eslint 신규 오류 0 | vitest·tsc·eslint 기준선 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 실 E2E — Opus 5.5 에이전트(data_analysis + excel_export)로 같은 요청이 엑셀 생성까지 성공한다
- [ ] SC-2: 생성 엑셀의 연체 69행·지점/상품 합계·최대 연체일수가 원천 직접 계산과 일치하고, 평균 금리가 비율 값(서식 `0.0%`)으로 채워진다
- [ ] SC-3: Opus 5.5에서 수퍼바이저·검색 판단 구조화 출력이 400 없이 동작한다(구형 모델 payload는 그대로)
- [ ] SC-4: Opus 5.5 분석 응답이 출력 한도 미설정 기본값 16000에서 text를 포함한다. 관리자가 저장한 값이 실제 요청 `max_tokens`로 전달된다
- [ ] SC-5: 같은 워커를 연속 상한 넘게 고르면 최종 답변으로 끝나고 사유가 기록된다
- [ ] SC-6: E2E 실행의 ai_llm_call에 provider·model_name·prompt/completion 토큰이 채워진다
- [ ] SC-7: 집계 결과가 전부 빈 컬럼이 있으면 답변 요약에 경고가 나간다
- [ ] 단위·계약 테스트 작성·통과 (TDD), 프론트 테스트 통과

### 4.2 Quality Criteria

- [ ] 신규·변경 함수 40줄 이하, if 중첩 2단계 이하
- [ ] `verify-architecture`, `verify-logging`, `verify-tdd` 통과
- [ ] 백엔드 영향 범위 회귀 + master 상시 실패 목록 외 신규 실패 0
- [ ] 프론트 vitest 상시 실패 목록 외 신규 실패 0, tsc·eslint 기준선 대비 신규 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| json_schema 전환 후 일부 스키마가 Anthropic 구조화 출력 제약(지원하지 않는 JSON Schema 키워드 등)에 걸려 400 | High | Medium | FR-11 정적 검사로 41곳 스키마 전수 확인. 위반 스키마는 LLM 전용 Draft로 분리([[llm-output-trust-boundary]]). Design에서 대표 스키마 실호출 프로브 |
| 큰 출력 한도에서 SDK 비스트리밍 거부 또는 장시간 요청 | Medium | Medium | FR-07 타임아웃 명시, 범위 검증(≤128000), Design에서 64000 실호출 확인 |
| 연속 호출 상한이 정상적인 재호출(검색 → 분석 → 검색은 연속이 아님, 같은 워커 2회 연속은 막히지 않음)을 막음 | Medium | Low | "연속" 기준으로만 세고 다른 워커가 끼면 리셋. 기본 2, 설정으로 조정 |
| 사용량 콜백 변경이 OpenAI 비용 계산을 바꿈 | Medium | Low | 키 기반 판정이 OpenAI 키를 그대로 처리함을 테스트로 고정, 기존 콜백 테스트 무회귀 |
| V092와 다른 브랜치 마이그레이션 번호 충돌 | Low | Medium | 작업 시작·PR 직전 `db/migration` 최신 번호 재확인 (agent-token-limit 교훈) |
| langchain-anthropic 버전 업 시 `with_structured_output`·기본 max_tokens 동작 변화 | Low | Low | 래핑은 메서드 하나로 국소화, payload 단위 테스트로 고정 |
| 거부 모델 목록이 새 모델 출시마다 낡음 | Medium | High | 이름 형식을 모르는 신형은 거부로 간주(안전한 기본값). 구형(4.x 이하·3.x)만 명시 허용 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `idt/src/domain/excel_generator/spec_policies.py` | Domain Policy | `%` 해석 추가 |
| `idt/src/infrastructure/excel_generator/{ops_executor,generator}.py`, `domain/excel_generator/schemas.py`, `workflow_compiler._render_excel_summary` | Infra/Schema/Node | 빈 컬럼 감지·경고 |
| `llm_model` 테이블 | DB | `max_output_tokens INT NULL` (V092) |
| `LlmModel` 엔티티·ORM·리포지토리·`application/llm_model/schemas.py` | Domain/Infra/API | 필드 추가(additive) |
| `idt/src/infrastructure/llm/llm_factory.py` | Infra | 출력 한도·타임아웃 전달, 구조화 출력 기본 방식 |
| `idt/src/domain/llm/sampling_policy.py`(또는 신규 정책 모듈) | Domain Policy | 강제 tool 호출 지원 판정 |
| `idt/src/application/pii_masking/guarded_llm.py` | Application | 프록시 경유 동작 확인(필요 시 수정) |
| 수퍼바이저 상태·노드(`supervisor_state.py`, `supervisor_nodes.py`) | Application | 연속 호출 추적·안내·종료 |
| `idt/src/infrastructure/llm/usage_callback.py` | Infra | 모델명·토큰 추출 |
| `idt/src/config.py` | Config | `anthropic_default_max_output_tokens`, Anthropic 요청 타임아웃, 워커 연속 호출 상한 |
| `idt_front/src/types/llmModel.ts`, 서비스, `pages/AdminLlmModelsPage` | Frontend | 출력 한도 입력·표시 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `LLMFactory.create` | CALL | main.py DI(대화·에이전트·유틸리티 provider·PII 팩토리), WorkflowCompiler | Needs verification — Anthropic payload 변경 |
| `with_structured_output` | CALL | 30개 파일 41곳(수퍼바이저·검색·수집·액션 파이프라인, 의도, 환각, 프롬프트 가드, 그래프 RAG, 시각화 등) | Needs verification — 거부 모델에서만 방식 변경 |
| `LlmModel` / `llm_model` | READ | 모델 레지스트리 API, 유틸리티 provider, 비용 계산, 시드 | None — additive |
| `LlmModel` | CREATE/UPDATE | 관리자 API·화면, `seed_default_models` | Needs verification — 새 필드 기본 NULL |
| 수퍼바이저 라우팅 | CALL | 모든 조립 에이전트 실행(REST·WS·승인 재개·서브 에이전트) | Needs verification — 연속 상한 |
| `UsageCallback` | CALL | 모든 LLM 호출 비용 기록 | Needs verification — OpenAI 무회귀 |
| `clean_numeric_text` | CALL | ops 실행기 filter·sort·groupby, `coerce_cell` | Needs verification — 퍼센트 값 비교 의미 변화 |

### 6.3 Verification

- [ ] 위 소비자 영향 범위 테스트 무회귀
- [ ] API 계약 변경(additive)에 맞춰 프론트 타입 동기화 (`/api-contract-sync`)
- [ ] 권한 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain → application → infrastructure) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 퍼센트 문자열 의미 | 비율(0.089) / 숫자(8.9) | 비율 | percent 서식(`0.0%`)과 정합, `coerce_cell`과 일치 (사용자 확정) |
| 출력 한도 저장 위치 | 설정값 1개 / DB 컬럼 / langchain 기본값 보정 | DB 컬럼 `max_output_tokens` + Anthropic NULL 기본 16000 | 모델별 관리, 관리자 화면에서 조정 (사용자 확정) |
| 큰 출력 한도 | 타임아웃 명시로 허용 / 안전 상한으로 자름 | 타임아웃 명시로 허용 | 관리자 설정값 존중 (사용자 확정) |
| 구조화 출력 전환 범위 | 거부 모델만 / 모든 Anthropic | 거부 모델만 | 구형 모델 회귀 위험 최소 (사용자 확정) |
| 구조화 출력 전환 위치 | 호출 지점 41곳 / 팩토리 중앙 | 팩토리 중앙 | 호출 지점 무수정, 새 지점 자동 적용 |
| 반복 루프 방지 | 연속 상한+안내+강제 종료 / 워커별 총 상한 / 제외 | 연속 상한+안내+강제 종료 | 정상 재호출(다른 워커 사이)은 허용 (사용자 확정) |
| 진행 방식 | 1사이클 모듈 5개 PR 1개 / 모듈별 PR | 1사이클 PR 1개 | 사용자 확정 |

### 7.3 Clean Architecture Approach

```
domain/        모델별 정책(temperature·강제 tool 호출·출력 한도 기본), 퍼센트 해석, 연속 호출 정책
application/   수퍼바이저 연속 호출 추적·안내·종료, PII 프록시
infrastructure/ LLMFactory(출력 한도·타임아웃·구조화 출력 방식), UsageCallback, 엑셀 생성기, llm_model ORM·리포지토리
interfaces/    llm_model API 스키마(additive)
idt_front/     types·서비스·관리자 모델 화면
```

---

## 8. Convention Prerequisites

- [x] `CLAUDE.md`(루트·idt·idt_front), `idt/docs/rules/*`
- [x] DDL COMMENT 규칙(`tests/db/test_migration_ddl_comments.py`)
- [x] API 계약 동기화 규칙(루트 CLAUDE.md §4-1)
- [x] 프론트 상수 export 규칙(메모리 `idt-front-const-export-rule`)

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope |
|----------|---------|-------|
| `ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS` | Anthropic 출력 한도 미설정 기본(16000) | Server (선택) |
| `SUPERVISOR_MAX_CONSECUTIVE_WORKER_CALLS` | 같은 워커 연속 호출 상한(기본 2) | Server (선택) |

---

## 9. Next Steps

1. [ ] Design (`/pdca design claude-agent-e2e-fixes`) — 거부 모델 목록·이름 판정 규칙, json_schema 래핑 방식(서브클래스 vs 래퍼)과 PII 프록시 상호작용, Anthropic 스키마 제약 검사 방법, 타임아웃 값, 연속 호출 상태 키·종료 경로, 사용량 콜백 추출 순서, 빈 컬럼 경고 문구, E2E 재현 스크립트 위치
2. [ ] 구현 (TDD, worktree `wt/claude-agent-e2e-fixes`)
3. [ ] 실 E2E 재실행 → Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft — 실 E2E 결함 5건, 사용자 확정 결정 7건 반영 | 배상규 |
