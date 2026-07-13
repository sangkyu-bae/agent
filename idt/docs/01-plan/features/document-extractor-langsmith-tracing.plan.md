# Plan: document-extractor-langsmith-tracing

> Created: 2026-07-06
> Status: Do (간단 작업 — Plan 직후 즉시 구현)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 문서추출기(document_extractor)의 LLM 호출 2곳(슬롯 추출/재추천 `SlotExtractor`, 문서 합성 `DocumentComposer`)이 LangSmith에 추적되지 않아 프롬프트/응답 디버깅이 불가능하다. |
| **Solution** | 기존 `agent-composer` 추적과 동일한 per-run `LangChainTracer` 패턴으로, 고정 프로젝트 `document-extractor` 아래 `slot-extract` / `slot-refine` / `compose:{템플릿명}` run_name으로 기록한다. |
| **Function UX Effect** | LangSmith에서 문서추출기 전용 프로젝트로 분리 조회 가능. run_name·request_id 메타데이터로 어떤 요청의 어떤 단계인지 즉시 식별. |
| **Core Value** | 전역 환경변수 변경 없이(동시성 race 없음) 문서추출기 LLM 품질 문제를 추적 가능한 관측성 확보. API 키 없으면 무동작(best-effort)이라 본 흐름 무영향. |

## 1. 배경

- `src/infrastructure/langsmith/langsmith.py`에 per-run tracer 패턴이 이미 존재:
  - `_make_project_tracer(project_name, tags)` — 키 없으면 None (본 흐름 영향 없음)
  - 사용례: `make_composer_tracer`(agent-composer), `make_agent_run_tracer`(agent-{name})
- 문서추출기 LLM 호출부는 `config=` 없이 `llm.ainvoke(messages)`만 호출 → 추적 누락.

## 2. 범위

### 대상 (LLM 호출 2곳)
1. `src/infrastructure/document_extractor/slot_extractor.py` — `_suggest()`
   - `extract()` → run_name `slot-extract`, `refine()` → run_name `slot-refine`
2. `src/infrastructure/document_extractor/composer.py` — `_decide_slot_values()`
   - run_name `compose:{template.name}`, metadata에 template_id 포함

### 변경 파일
| 파일 | 변경 |
|------|------|
| `src/infrastructure/langsmith/langsmith.py` | `DOCUMENT_EXTRACTOR_PROJECT_NAME = "document-extractor"` 상수 + `make_document_extractor_tracer()` 추가 |
| `src/infrastructure/document_extractor/slot_extractor.py` | `_suggest`에 trace config(run_name/tags/metadata/callbacks) 주입 |
| `src/infrastructure/document_extractor/composer.py` | `_decide_slot_values`에 trace config 주입 |
| `tests/infrastructure/langsmith/test_langsmith_helpers.py` | tracer 헬퍼 테스트 추가 |
| `tests/infrastructure/document_extractor/test_slot_extractor.py` | FakeLLM config 수용 + run_name 검증 |
| `tests/infrastructure/document_extractor/test_composer.py` | FakeLLM config 수용 + run_name 검증 |

### 제외 (Out of Scope)
- MCP 변환(`document_conversion_adapter`) 추적 — LLM 아님
- 전역 `LANGSMITH_PROJECT` 환경변수 방식 — race 유발, 기존 per-run 패턴 유지

## 3. 설계 결정

- **프로젝트명 고정**: `document-extractor` (composer의 `agent-composer` 선례와 동일한 고정 프로젝트 방식)
- **run_name 규칙**: 단계별 식별 — `slot-extract` / `slot-refine` / `compose:{템플릿명}`
- **metadata**: `request_id` 공통, compose는 `template_id` 추가
- **API 키 부재 시**: tracer None → callbacks 미설정, run_name/metadata만 config로 전달 (기존 패턴 그대로)

## 4. TDD 절차

1. Red: 헬퍼/추출기/합성기 테스트에 config 캡처 + run_name 검증 추가 → 실패 확인
2. Green: 헬퍼 추가 + 호출부 2곳에 config 주입
3. 회귀: `tests/infrastructure/document_extractor/`, `tests/infrastructure/langsmith/` 통과 확인

## 5. 후속 조치 (2026-07-06 — 429 인시던트)

첫 실사용에서 `429 Too Many Requests`(입력 39,289 토큰 > gpt-4o TPM 30,000) 발생.
확인 결과 LangSmith 기록 자체는 정상 동작(document-extractor 프로젝트에 에러 run 존재).
다음을 추가 수정:

1. **LLM 입력 상한**: `document_extractor_llm_html_max_chars`(기본 20000자) 설정 추가,
   `SlotExtractor`가 프롬프트용 HTML만 절단(반환 HTML/템플릿 원본은 그대로).
2. **에러 매핑**: LLM 호출 실패(429 등)를 `SlotExtractionFailedError`로 감싸
   라우터가 502 `{code, message}`로 응답 → UI에 원인 표시.
3. **프론트 에러 표시 버그**: 에러 메시지가 `{draft && ...}` 블록 안에 있어
   업로드 실패 시 렌더링되지 않던 것을 블록 밖으로 이동.
4. **authClient**: FastAPI `detail`이 `{code, message}` 객체인 경우 message 추출.
5. **진단성**: LangSmith 키 부재로 tracer가 None이면 서버 로그에 warning 1회 기록.

## 6. 리스크 / 영향

- `FakeLLM.ainvoke(messages)` 시그니처가 `config=` 키워드를 받도록 테스트 수정 필요 (프로덕션 LangChain LLM은 `ainvoke(input, config=None)` 표준 시그니처라 호환)
- 레이어 규칙 준수: infrastructure → infrastructure 참조만 발생 (domain 오염 없음)
