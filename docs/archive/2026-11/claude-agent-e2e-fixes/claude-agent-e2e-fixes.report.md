# claude-agent-e2e-fixes Completion Report

> Feature: claude-agent-e2e-fixes · Date: 2026-11-19 · Match Rate: 97% (Act-1 1회)
> Branch: `fix/claude-agent-e2e-fixes` (worktree `wt/claude-agent-e2e-fixes`, base master `aae4565`)

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 출발점 | 2026-11-19 실 E2E — Claude 에이전트(data_analysis + excel_export)로 여신 현황 엑셀 → 팀장 보고용 엑셀 요청 |
| 발견 결함 | 5건: 퍼센트 문자열 집계 빈칸, Opus 5.5 출력 4096 제한, 구조화 출력 400, 같은 워커 반복 루프, Claude 호출 비용 기록 unknown/0 |
| 범위 | 백엔드(도메인 정책 2개·하위 클래스 1개·V092 컬럼·수퍼바이저) + 관리자 모델 화면, 7개 모듈, PR 1개 |
| 설계안 | Option C (실용 균형) |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| Match Rate | 96% → 97% (Act-1) |
| Success Criteria | 6/7 충족, 1 부분 충족(SC-4, 수용) |
| 실 E2E (Opus 5.5) | HTTP 200, 274초, LLM 9회, 산출 엑셀 3시트 값·서식 기대값과 전부 일치 |
| 테스트 | 백엔드 회귀 6082 passed, 프론트 262 passed, tsc 기준선(210) 유지 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | 최신 Claude 모델(Opus 5.5·Sonnet 5.5·Fable 5.x)을 고른 에이전트는 수퍼바이저 라우팅부터 400으로 실패했다. 구형 모델에서도 분석 워커를 13회 반복 호출해 약 $2를 썼고, 퍼센트 열 평균은 빈칸, 비용 기록은 0이었다 |
| Solution | forced tool 호출을 거부하는 모델만 구조화 출력을 `json_schema`로 바꾸고, 모델별 출력 한도 컬럼(`max_output_tokens`)을 추가했다. 같은 워커 연속 호출 상한, `%` 문자열의 비율 해석과 빈 컬럼 경고, 스트리밍 응답의 모델명·토큰 추출, 분석 빈 답 처리를 넣었다 |
| Function UX Effect | 같은 요청이 Opus 5.5에서 끝까지 동작해 연체 69행·지점/상품 합계·평균 금리(0.0% 서식)가 원천 계산과 일치하는 엑셀이 나온다. 관리자는 모델 화면에서 최대 출력 토큰을 정할 수 있고, ai_llm_call에 모델명과 입출력 토큰이 남는다 |
| Core Value | 관리자가 모델을 최신 Claude로 바꿔도 에이전트가 깨지지 않고, 실패하면 원인(출력 한도 도달 등)을 드러낸다. 41개 구조화 출력 호출 지점은 수정하지 않았다 |

## 1.4 Success Criteria Final Status

| SC | 상태 | 근거 |
|----|:---:|------|
| SC-1 E2E가 엑셀 생성까지 성공 | ✅ | `idt/scripts/e2e_claude_excel_report.py` — HTTP 200, `excel_export_worker` 파일 생성 |
| SC-2 연체 69행·합계·최대 연체·평균 금리 비율 | ✅ | 검증 PASS: 69행 내림차순(최대 175), 지점 5·상품 3 값 일치, 금리 서식 `0.0%` |
| SC-3 Opus 5.5 구조화 출력 400 없음 | ✅ | 수퍼바이저 결정 4회 정상, 구형 payload 불변 테스트 F1/F2 |
| SC-4 기본 16000에서 분석 응답 text 포함 / 저장값 전달 | ⚠️ 부분 | 저장값 → `max_tokens` 전달은 충족. 입력 58k 분석 호출에서는 16000이 전부 thinking으로 소진 → 빈 답 처리만 추가하고 한도는 모델별 설정으로 해소(사용자 결정) |
| SC-5 연속 상한 초과 시 종료·사유 기록 | ✅ | 단위 테스트 S3 (`__end__`, 단계 요약 `[반복 상한]`, warning 로그). 실 E2E에서는 연속 반복이 없어 미발동 |
| SC-6 ai_llm_call 모델명·토큰 | ✅ | 9건 전부 `claude-opus-5-5`·토큰 기록, unknown 0 |
| SC-7 빈 컬럼 경고 | ✅ | 요약 경고·`empty_columns` 테스트 |

**Overall: 6/7 충족 (1 부분 충족, 수용)**

## 1.5 Decision Record Summary

| 결정 | 결과 |
|------|------|
| `%` 문자열은 비율(0.089)로 읽고 빈 컬럼은 경고 | 평균 금리가 비율로 채워지고 `0.0%` 서식으로 표시됨 |
| 출력 한도는 DB 컬럼, NULL이면 Anthropic만 16000 | 적용. 구형 Anthropic 모델의 기본 출력이 langchain 기본(64000~128000)에서 16000으로 낮아짐 — 필요 시 모델별로 올림 |
| 큰 출력 한도 + 요청 타임아웃 명시 | 변경 — 실호출에서 64000·128000이 타임아웃 없이 정상이라 FR-07 삭제 |
| `json_schema`는 forced tool 거부 모델만 | 적용. 이름 형식을 모르는 신형은 거부로 간주. PII 프록시 경유도 동작 |
| 연속 호출 상한 + 안내 → 그래도 고르면 종료 | 적용(기본 2, 0이면 비활성). 프론트 payload 불변 |
| Option C 실용 균형 | 도메인 정책 2개, 하위 클래스 1개, 기존 노드·팩토리 확장으로 끝남 |
| Check G-1: 빈 답 처리만 (한도 상향 안 함) | `EmptyLLMResponseError` — 분석 노드가 검색 판단·환각 검사 전에 원인을 담아 실패 |

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/claude-agent-e2e-fixes.plan.md` |
| Design | `docs/02-design/features/claude-agent-e2e-fixes.design.md` |
| Analysis | `docs/03-analysis/claude-agent-e2e-fixes.analysis.md` |
| Report | 이 문서 |

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 |
|----|------|:---:|
| FR-01 | `clean_numeric_text`가 `%` 접미 문자열을 /100 비율로 해석 | ✅ |
| FR-02 | 값이 전부 빈 컬럼을 `ExcelGenerateResult.empty_columns`에 담고 요약에 경고 | ✅ |
| FR-03 | V092 `llm_model.max_output_tokens INT NULL` + 모델 `comment=` | ✅ |
| FR-04 | 엔티티·리포지토리·생성/수정/응답 스키마(1~128000) | ✅ |
| FR-05 | 프론트 타입·관리자 화면 "최대 출력 토큰", 기존 라벨 "컨텍스트 크기" | ✅ |
| FR-06 | `LLMFactory` provider별 출력 한도 전달, Anthropic NULL → 16000 | ✅ |
| FR-07 | Anthropic 요청 타임아웃 | 삭제 |
| FR-08 | `anthropic_supports_forced_tool_choice` | ✅ |
| FR-09 | 거부 모델은 `JsonSchemaStructuredChatAnthropic` (호출 지점 무수정) | ✅ |
| FR-10 | `PiiGuardedLLMFactory` 경유 적용 | ✅ |
| FR-11 | 구조화 출력 스키마 정적 검사(위반 0) | ✅ |
| FR-12 | 연속 호출 추적 + 상한 안내 블록 | ✅ |
| FR-13 | 상한 후 같은 워커 선택 시 종료 + 사유 기록 | ✅ |
| FR-14 | 사용량 콜백 모델명 추출 순서(llm_output → 메시지 메타 → params → 시작 시 기록) | ✅ |
| FR-15 | 토큰 정규화 키 기반 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| 하위 호환 | 상한 0·저장값 NULL(비 Anthropic)이면 기존 동작 바이트 동일, API 응답 필드 additive |
| 레이어 | 판정 로직은 domain(`sampling_policy`, `worker_repeat_policy`, `spec_policies`, 예외), LangChain 의존은 infrastructure |
| DDL | 전 컬럼 COMMENT, 검사 테스트 통과 |
| lint | 수정 src 파일 master 대비 E501/F 증가 없음 |

### 3.3 Deliverables

| 종류 | 경로 |
|------|------|
| 마이그레이션 | `idt/db/migration/V092__add_max_output_tokens_to_llm_model.sql` |
| 신규 모듈 | `idt/src/domain/agent_builder/worker_repeat_policy.py`, `idt/src/infrastructure/llm/structured_chat_anthropic.py` |
| E2E 스크립트 | `idt/scripts/e2e_claude_excel_report.py` (수동 실행, 비용 경고) |
| 신규 테스트 | worker_repeat_policy, supervisor_repeat_guard, structured_chat_anthropic, structured_output_schemas_anthropic(계약), max_output_tokens, 빈 분석 응답 등 |
| 프론트 | `idt_front/src/types/llmModel.ts`, `idt_front/src/pages/AdminLlmModelsPage/index.tsx` (+test) |

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 내용 |
|------|------|
| 분석 워커 입력 크기 | 600행 원문이 프롬프트에 들어가 입력 58k. thinking 상시 모델에서 16000 출력이 추론에 소진된다. 원문 대신 요약·통계를 넣거나 effort를 낮추는 방안 검토 |
| 수퍼바이저 비연속 재호출 | 엑셀 생성이 끝난 뒤 실패했던 분석 워커를 한 번 더 호출(분석 → 엑셀 → 분석). 연속 상한으로는 막히지 않음 |
| G-2 | 결정 실패 종료 경로의 반복 상태 미리셋 (실영향 없음) |

### 4.2 Cancelled/On Hold Items

- FR-07 Anthropic 요청 타임아웃 — 실측 근거로 삭제.

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:---:|
| Structural | 100% |
| Functional | 96% |
| Contract | 100% |
| Runtime | 93% |
| Overall | 97% (Act-1 후) |

### 5.2 Resolved Issues

| 결함 | 해결 |
|------|------|
| 퍼센트 집계 빈칸 | `%` 비율 해석 + 빈 컬럼 경고 |
| Opus 5.5 출력 4096 | 모델별 출력 한도 + Anthropic 기본 16000 |
| 구조화 출력 400 | 거부 모델만 json_schema |
| 같은 워커 반복 루프 | 연속 호출 상한(기본 2) |
| 비용 기록 unknown/0 | 시작 시 모델 기록·메시지 메타 폴백·키 기반 토큰 |
| (E2E 중 발견) 분석 빈 답이 환각 검사 오류로 둔갑 | `EmptyLLMResponseError`로 원인 노출 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 실 E2E로 단위 테스트가 놓친 결함을 찾고, 같은 스크립트로 수정을 확인했다.
- Design 단계의 실호출 확인(max_tokens 64000·128000, json_schema 동작)으로 타임아웃 요구사항을 근거 있게 뺐다.
- 구조화 출력 호출 지점 41곳을 건드리지 않고 팩토리에서 하위 클래스를 고르는 방식으로 영향 범위를 줄였다.

### 6.2 What Needs Improvement (Problem)

- 출력 한도 기본값 16000을 정할 때 대용량 입력 + thinking 상시 모델 조합을 실측하지 않았다.
- E2E 스크립트가 Windows cp949 콘솔에서 답변 이모지 출력 시 종료됐다(결과 저장 후라 재검증만 다시 함).

### 6.3 What to Try Next (Try)

- 기본값을 정하는 요구사항은 가장 무거운 실사용 입력으로 1회 실측한 뒤 확정한다.
- 실 E2E 스크립트는 결과를 먼저 저장하고, 출력 인코딩을 처음부터 UTF-8로 고정한다.

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- 실 LLM이 관여하는 기능은 Plan의 SC에 "실 모델 1회 실행"을 넣고, Check에서 그 결과로 Runtime 점수를 매긴다(이번 사이클 방식 유지).

### 7.2 Tools/Environment

- 저장된 run 결과로 다운로드·검증·DB 조회만 다시 하는 모드를 E2E 스크립트 옵션으로 두면 재실행 비용을 줄일 수 있다.

## 8. Next Steps

### 8.1 Immediate

- 커밋·PR (사용자 요청 시). PR 본문에 V092 운영 적용 필요, 구형 Anthropic 기본 출력 16000 변경을 명시.
- 운영 배포 시 Opus 5.5 등 thinking 상시 모델은 "최대 출력 토큰"을 작업량에 맞게 설정.

### 8.2 Next PDCA Cycle

- 분석 워커 입력 축소(원문 대신 요약·통계) 또는 effort 조절.
- 수퍼바이저가 완료 후 실패 워커를 다시 부르는 비연속 재호출 억제.

## 9. Changelog

### v1.0.0 (2026-11-19)

- Added: `llm_model.max_output_tokens`(V092), 관리자 화면 "최대 출력 토큰", 수퍼바이저 연속 호출 상한(`supervisor_max_consecutive_worker_calls`, 기본 2), `JsonSchemaStructuredChatAnthropic`, `EmptyLLMResponseError`, E2E 스크립트
- Changed: Anthropic 모델 출력 한도 기본 16000(설정 `anthropic_default_max_output_tokens`), `%` 문자열을 비율로 해석, 관리자 화면 "최대 토큰 수" → "컨텍스트 크기 (최대 토큰)"
- Fixed: 최신 Claude 구조화 출력 400, Claude 호출 비용 기록 unknown/0, 퍼센트 열 집계 빈칸, 분석 빈 답이 환각 검사 오류로 나타나던 문제

## Version History

| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0 | 2026-11-19 | 최초 작성 |
