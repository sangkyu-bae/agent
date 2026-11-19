# claude-agent-e2e-fixes — Gap Analysis

> Feature: claude-agent-e2e-fixes · Phase: Check · Date: 2026-11-19
> Plan: `docs/01-plan/features/claude-agent-e2e-fixes.plan.md` · Design: `docs/02-design/features/claude-agent-e2e-fixes.design.md` (Option C)
> Worktree: `wt/claude-agent-e2e-fixes` (branch `fix/claude-agent-e2e-fixes`, 미커밋)

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 실 E2E에서 최신 Claude 에이전트가 라우팅 400·빈 답·반복 루프로 동작하지 않았고, 엑셀 집계 빈칸과 비용 추적 0이 조용히 감춰졌다 |
| **WHO** | P2(에이전트 소유자) — 관리자가 등록한 모델로 에이전트를 만들고 결과물(엑셀 등)을 받는 사용자, 그리고 사용량·비용을 보는 관리자 |
| **RISK** | json_schema 전환 시 Anthropic 스키마 제약 위반(41개 호출 지점), 큰 출력 한도의 SDK 비스트리밍 거부, 연속 호출 상한이 정상 재호출을 막음, V092 운영 적용 순서 |
| **SUCCESS** | 같은 E2E 시나리오(Opus 5.5, data_analysis + excel_export)가 끝까지 성공하고 엑셀 값이 원천 직접 계산과 일치, 평균 금리 채워짐, 반복 호출이 상한에서 멈춤, ai_llm_call에 모델명·입출력 토큰 기록 |
| **SCOPE** | 5개 모듈: M1 퍼센트·빈 컬럼 / M2 출력 한도(DB·API·관리자 화면·팩토리) / M3 구조화 출력 / M4 반복 루프 / M5 비용 추적. PR 1개 |

---

## 1. 결과 요약

| 축 | 점수 | 근거 |
|----|:---:|------|
| Structural | 100% | Design §11.1의 신규 6·수정 파일 전부 존재 (32파일 수정 + 신규 11) |
| Functional | 96% | FR 14건(FR-07 Dropped 제외) 구현·테스트 확인. 경미 1건(§4 G-2) |
| Contract | 100% | `max_output_tokens` 백엔드 스키마 ↔ `idt_front/src/types/llmModel.ts` 3개 타입 일치, 응답 additive |
| Runtime | 93% | 실 E2E 1회 실행(Opus 5.5) + 단위·회귀. SC 7건 중 6 충족, 1 부분(SC-4) |
| **Overall** | **96%** | 0.15·100 + 0.25·96 + 0.25·100 + 0.35·93 |

---

## 2. Success Criteria

| SC | 상태 | 근거 |
|----|:---:|------|
| SC-1 E2E가 엑셀 생성까지 성공 | ✅ | `scripts/e2e_claude_excel_report.py` 실행: HTTP 200, 274초, 단계 15개, `excel_export_worker` 파일 생성 |
| SC-2 연체 69행·합계·최대 연체·평균 금리 비율 | ✅ | 검증 PASS — 연체 69행 내림차순(최대 175), 지점 5개 건수·잔액·평균금리(0.0747 등, 서식 `0.0%`), 상품 3개 잔액·최대 연체 전부 기대값과 일치 |
| SC-3 Opus 5.5 구조화 출력 400 없음 | ✅ | 수퍼바이저 결정 4회 정상(400 없음). 구형 payload 불변은 `test_llm_factory_anthropic_sampling.py` F1/F2, 하위 클래스는 `test_structured_chat_anthropic.py` F5/F6 |
| SC-4 기본 16000에서 분석 응답에 text 포함 / 저장값 전달 | ⚠️ 부분 (수용, Act-1) | 저장값 → `max_tokens` 전달은 F1~F4로 충족. **분석 워커 호출 2회가 입력 58k·출력 16000을 전부 thinking으로 써 text 0** (§3 G-1) |
| SC-5 연속 상한 초과 시 종료·사유 기록 | ✅ | `test_supervisor_repeat_guard.py` S3: `__end__` + 단계 요약 `[반복 상한] …` + warning 로그. 실 E2E에서는 연속 반복이 발생하지 않아 미발동(분석→엑셀→분석은 비연속) |
| SC-6 ai_llm_call 모델명·토큰 | ✅ | 9건 전부 `claude-opus-5-5`, prompt/completion 토큰 기록, unknown 0건 |
| SC-7 빈 컬럼 경고 | ✅ | `test_workflow_compiler_excelgen.py` 요약 경고, `test_generator.py` empty_columns |

---

## 3. Gaps

### G-1 (Critical — SC-4 부분 충족) Opus 5.5 분석 워커 빈 답

- **현상**: `data_analysis_worker` 2회 모두 "엑셀 분석 실패: Generation and documents are required".
- **원인 1 (출력 한도)**: 600행 원문이 프롬프트에 들어가 입력 58k. Opus 5.5(thinking 상시)가 출력 16000을 전부 추론에 써 텍스트가 비었다. 4096 → 16000으로 올렸지만 이 작업량엔 부족.
- **원인 2 (빈 답 처리 없음)**: `excel_analysis_workflow._evaluate_node`가 빈 `analysis_text`를 그대로 `HallucinationEvaluatorUseCase.evaluate`에 넘기고, 이 함수가 `ValueError`를 던져 워크플로가 깨진다(`src/application/hallucination/use_case.py:44`). 사용자·로그에 "출력 한도 도달"이라는 원인이 드러나지 않는다.
- **영향**: 최종 결과물은 정확(수퍼바이저가 실패를 보고 엑셀 생성으로 진행, 최종 답변도 분석 실패를 사실대로 고지). 다만 분석 2회가 출력 16000씩 버려 비용 낭비.
- **선택지**: (a) 빈 답 가드 — 빈 text면 환각 검사를 건너뛰고 "출력 한도 도달"을 워커 결과·로그에 남김 (b) (a) + Anthropic 기본 출력 한도 상향 (c) 기록만 하고 다음 사이클. (a)만으로는 SC-4 text 조건이 충족되지 않는다 — 한도 상향이나 관리자 모델별 설정이 필요.

### G-2 (Minor) 결정 실패 종료 경로의 반복 상태 미리셋

- Design §5.4 "종료 반환은 ("", 0)로 리셋" — 수퍼바이저 LLM 결정 예외 경로(`supervisor_nodes.py` `except` 블록)는 `repeat_worker_*`를 갱신하지 않는다.
- 이 경로는 `__end__`로 런을 끝내므로 같은 런에서 다시 읽히지 않는다. 실영향 없음.

---

## 4. Decision Record 검증

| 결정 | 준수 | 비고 |
|------|:---:|------|
| [Plan] 퍼센트 = 비율 + 빈 컬럼 경고 | ✅ | `clean_numeric_text` `%`→/100, `ExcelGenerateResult.empty_columns` |
| [Plan] 출력 한도 = DB 컬럼, NULL이면 Anthropic만 16000 | ✅ | V092 + `resolve_max_output_tokens`, OpenAI·Ollama는 저장값 있을 때만 |
| [Plan→Design] 큰 값 허용 + 타임아웃 | 변경 | FR-07 Dropped — 실호출에서 64000·128000이 타임아웃 없이 정상 |
| [Plan] json_schema는 forced tool 거부 모델만 | ✅ | `anthropic_supports_forced_tool_choice` + `JsonSchemaStructuredChatAnthropic`, 호출 지점 무수정 |
| [Plan] 연속 상한 + 안내 → 그래도 고르면 종료 | ✅ | 기본 2, 0이면 비활성(프롬프트 바이트 동일), `limit_reached` 미설정으로 프론트 payload 불변 |
| [Design] Option C 실용 균형 | ✅ | domain 정책 2개 신규, 하위 클래스 1개, 기존 노드·팩토리 확장 |
| [Plan] 1사이클·PR 1개 | 진행 중 | 미커밋 |

---

## 5. 검증 실행 기록

- 백엔드 회귀: `tests/application/agent_builder tests/application/agent_run tests/domain tests/contracts tests/application/pii_masking tests/infrastructure/llm tests/infrastructure/excel_generator tests/application/llm_model tests/api/test_excel_preview_wiring.py` → **6082 passed, 2 skipped**. 줄바꿈 정리 후 agent_builder·domain 1766 passed.
- module-4 범위(db·llm_model·llm): 248 passed. DDL COMMENT 검사 통과.
- 프론트: `AdminLlmModelsPage` 18/18, LLM 모델 타입 사용 파일 262 passed(`--no-file-parallelism`), tsc 210(기준선 동일), eslint 0.
- lint: 수정 src 파일 모두 master 대비 E501/F 증가 없음.
- 실 E2E: Opus 5.5, data_analysis+excel_export, LLM 9회(입력 합 약 13.2만, 출력 합 약 3.5만 토큰). 로컬 DB에 V092 적용됨.

## 6. Act-1 (2026-11-19) — G-1 빈 답 가드

사용자 결정: "빈 답 가드만" (기본 출력 한도 16000 유지, 한도는 관리자가 모델별 "최대 출력 토큰"으로 조정).

- `src/domain/llm/exceptions.py`: `EmptyLLMResponseError.from_stop_reason()` — `max_tokens`면 "출력 한도에 도달 … '최대 출력 토큰'을 늘려 주세요", 그 외 "빈 응답 (stop_reason=…)".
- `src/application/workflows/excel_analysis_workflow.py` `_analyze_node`: 텍스트가 비면 검색 판단·환각 검사 전에 위 예외로 그래프를 멈춘다(재시도 없음 — 같은 한도에서 다시 빈다). 워커 쪽 기존 `except` 가 "엑셀 분석 실패: <원인>" 으로 수퍼바이저·런 단계에 전달.
- 테스트 `tests/application/test_excel_analysis_workflow.py::TestEmptyAnalysisResponse` 3건 (max_tokens 문구·검색 판단 미호출, stop_reason 없음, 환각 검사 미호출). 관련 회귀 1420 passed.
- G-1 상태: 원인 2(빈 답 처리) **해결**. 원인 1(16000 부족)은 **수용** — SC-4 text 조건은 기본값에선 대용량 입력 분석에서 미충족, 모델별 설정으로 해소하는 것으로 정리. 실 E2E 재실행은 하지 않음(비용).
- G-2: 수용(실영향 없음).

## 7. 다음 단계

- `/pdca report claude-agent-e2e-fixes`
