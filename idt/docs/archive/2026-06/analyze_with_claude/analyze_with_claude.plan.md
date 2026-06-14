# ANALYZE_WITH_CLAUDE: 분석 노드 프롬프트 엄격화 — 차트 책임 분리 + 출력 범위 고정

> 상태: Plan
> 연관 Task: ANALYZE-PROMPT-001
> 작성일: 2026-06-09
> 우선순위: High
> 대상 노드: `excel_analysis_workflow.py :: _analyze_node` (그래프 노드명 `analyze_with_claude`)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `analyze_with_claude` 노드의 시스템 프롬프트가 "당신은 데이터 분석 전문가입니다 / 데이터에 근거하세요" **2줄뿐**이라, "배상규 남은 휴가 알려주고 사용자별 남은 휴가 그래프로 그려줄 수 있니?" 같은 질문이 오면 분석 노드가 **분석 텍스트와 차트 JSON을 한꺼번에** 뱉는다. 그런데 이 프로젝트는 이미 `chart_router → chart_builder`라는 **차트 전담 경로**를 갖고 있어, 분석 노드가 JSON을 만들면 책임이 중복되고 하류가 오염된다. |
| **Solution** | 차트를 **만드는** 책임을 분석 노드에서 떼어내고, 분석 노드는 **자연어 분석 텍스트만** 생성하도록 프롬프트를 풍부하고 엄격하게 재작성한다. 그래프 요청이 와도 차트를 직접 그리지 않고, 차트가 쓸 **항목별 수치를 자연어로 나열**만 하게 한다(실제 차트는 하류 `chart_builder`가 생성). 추가로 도메인 정책에 **출력 새니타이저**를 두어, 프롬프트를 어기고 새어 나온 코드블록/JSON을 `analysis_text` 저장 전에 제거하는 2차 방어선을 둔다. |
| **Function UX Effect** | "그래프 그려줘"는 그대로 동작하되, 차트는 항상 정상 경로(`chart_router`가 본 깨끗한 수치 텍스트 → `chart_builder`)로만 만들어진다. 분석 노드가 임의로 던지던 JSON이 사라져 답변이 일관되고, 묻지 않은 추측·전망·추천이 붙지 않아 응답이 질문 범위 안에 머문다. |
| **Core Value** | **관심사 분리 강제** — "분석은 텍스트, 차트는 차트 노드"라는 그래프 설계 의도를 프롬프트와 정책으로 못박아 예측 가능성을 확보한다. 할루시네이션 평가(`evaluate_hallucination`)와 차트 라우팅(`chart_router`)이 깨끗한 자연어 텍스트만 받게 되어 파이프라인 정확도가 올라간다. |

---

## 1. 문제 정의 (Problem Statement)

대상: `src/application/workflows/excel_analysis_workflow.py`

현재 분석 노드의 프롬프트 (`_build_analysis_prompt`, line 283~300):

```python
return f"""당신은 데이터 분석 전문가입니다.

## 사용자 질문
{query}
## 엑셀 데이터
{excel_data}
## 웹 검색 결과 (있는 경우)
{web_context if web_context else "없음"}
## 지침
1. 데이터를 기반으로 정확하게 분석하세요
2. 추측하지 말고 데이터에 근거하세요"""
```

지침이 "정확하게 / 추측 말고" 2줄뿐이라 **출력 형식·역할 경계가 비어 있다.** 그래서:

```
[사용자] "배상규 남은 휴가 알려주고, 사용자별 남은 휴가 그래프로 그려줄 수 있니?"
   → analyze_with_claude 노드:
        "배상규 5일... (분석 텍스트)
         ```json { "type": "bar", "data": {...} }```"   ← 차트 JSON까지 같이 생성
```

분석 노드가 JSON을 만들면 하류가 깨진다:

1. **`evaluate_hallucination`** — `analysis_text`(자연어)를 엑셀 문서와 대조해 할루시네이션을 본다. 텍스트에 JSON 덩어리가 섞이면 평가 정확도가 떨어지고, 불필요한 retry 루프를 유발할 수 있다.
2. **`chart_router`** — `VisualizationRoutingPolicy.data_suggests_chart()`가 `analysis_text`의 **숫자 토큰 수**(임계 4개)로 차트 후보를 판단한다(`policies.py:31-36`). 인라인 JSON의 숫자가 카운트를 부풀려 라우팅이 오염된다.
3. **`chart_builder`** — 이 프로젝트에서 **차트 JSON을 만드는 유일한 노드**(`chart_builder_node.py`). 분석 노드가 별도 JSON을 만들면 **단일 책임 원칙과 그래프 설계 의도가 깨진다.**

요약: 차트를 그리는 경로는 이미 `chart_router → chart_builder`로 존재한다. **분석 노드는 그 길로 보낼 깨끗한 "수치가 담긴 자연어 텍스트"만 만들면 된다.** 지금은 프롬프트가 그것을 강제하지 못한다.

---

## 2. 현재 구조 분석 (Current State)

### 2-1. ExcelAnalysisWorkflow 그래프 배선 (`excel_analysis_workflow.py:93-144`)

```
parse_excel → analyze_with_claude
  → [_should_search] → web_search(루프) / evaluate_hallucination
evaluate_hallucination
  → [_should_retry_or_complete] → web_search(retry) / chart_router
chart_router
  → [route_after_chart_router] → chart_builder(visualize) / END(text)
chart_builder → END
```

- `analyze_with_claude`(`_analyze_node`, line 162)는 LLM 응답을 `analysis_text`로 저장한다(line 191-205). 이 텍스트가 **그대로 하류 3노드의 입력**이 된다.
- 차트 생성의 단일 소유자는 `chart_builder`(`viz_decision == "visualize"`일 때만 `state["charts"]`를 채움, `chart_builder_node.py:35-52`).
- `chart_router`/`chart_builder`는 모두 `extract_analysis_text(state)`로 `analysis_text`를 읽는다(`chart_extract.py:21-30`).

### 2-2. 핵심 사실

| 사실 | 근거 | 시사점 |
|------|------|--------|
| 분석 노드는 자연어 텍스트만 만들면 충분 | 하류에 차트 전담 노드 존재 | 분석 노드의 JSON 생성은 **불필요·유해** |
| 차트는 `analysis_text`의 수치를 보고 생성 | `chart_builder`가 `analysis_text` 입력 | 분석 텍스트에 **항목별 수치가 자연어로 있어야** 차트가 나온다 |
| 라우팅은 `analysis_text` 숫자 토큰 휴리스틱 | `policies.py:31-36` | 텍스트가 깨끗할수록 라우팅 정확 |
| 같은 패턴의 약한 프롬프트가 1곳 더 | `workflow_compiler.py:645` (supervisor analysis 노드) | 동일 하드닝 후보(§7 범위 외/후속) |

### 2-3. 제약 (CLAUDE.md)

- 아키텍처/레이어 이동 금지 → **그래프 구조·노드 추가는 하지 않는다.** 이번 작업은 프롬프트 강화 + 출력 새니타이즈(순수 규칙)로 한정.
- 비즈니스 "규칙"은 domain Policy에 둔다 → 출력 새니타이저는 `domain/visualization`에 순수 함수/정책으로.
- TDD 필수: 테스트 먼저(RED) → 구현(GREEN).
- config 하드코딩 금지: 프롬프트 본문은 상수화하되, 임계/토글이 필요하면 config 경유.

---

## 3. 수정 범위 (Scope)

| # | 위치 | 내용 | 레이어 | 우선순위 |
|---|------|------|--------|----------|
| 1 | `excel_analysis_workflow.py` `_build_analysis_prompt` | 풍부·엄격 프롬프트로 교체(역할 경계 + 출력 형식 제한 + 범위 고정 + 그래프 요청 처리 규칙). 본문은 모듈 상수화 | application | High |
| 2 | `src/domain/visualization/analysis_output_policy.py` (신규) | `AnalysisOutputSanitizer` — 코드블록/JSON 덩어리 제거하는 순수 정책 | domain | High |
| 3 | `_analyze_node` | LLM 응답을 `analysis_text`로 저장하기 전에 새니타이저 적용 | application | High |
| 4 | `tests/...` | 프롬프트 제약 회귀 테스트 + 새니타이저 단위 테스트 + 노드 통합 테스트 (TDD) | - | High |

**범위 외 (별도/후속)**:
- 그래프 구조·노드 추가/이동 (이미 `chart_router/chart_builder` 존재 → 손대지 않음)
- `workflow_compiler.py:645` supervisor analysis 노드 동일 하드닝 → 후속 Task 권장(동일 상수/정책 재사용)
- `chart_builder`의 수치 추출 정확도 개선 (별도 이슈)
- 프론트 변경 없음 (응답 스키마 불변 → `/api-contract-sync` 불필요)

---

## 4. 설계 (Solution Design)

### 4-1. 책임 경계 (핵심)

```
analyze_with_claude   = "수치가 담긴 자연어 분석 텍스트"만 생성   ← 차트 절대 생성 금지
        │  (analysis_text)
        ▼
chart_router          = 텍스트/질문 보고 visualize|text 판단
        │
        ▼
chart_builder         = analysis_text의 수치 → Chart.js config 생성   ← 차트의 유일한 소유자
```

그래프 요청("사용자별 남은 휴가 그래프로")이 와도 **분석 노드는 차트를 만들지 않는다.** 대신 차트가 쓸 항목별 수치를 자연어로 나열한다:

> "사용자별 남은 휴가 — 배상규 5일, 김철수 3일, 이영희 7일."

이 한 줄이면 `chart_builder`가 막대그래프를 만들 수 있다. 즉 **분석 노드는 "차트의 원재료(수치)"를 텍스트로 제공**하고, **차트 조립은 하류가 전담**한다.

### 4-2. 풍부·엄격 프롬프트 (제안안 — Design에서 확정)

`_build_analysis_prompt` 반환 본문을 아래로 교체한다. 본문은 `_ANALYSIS_GUIDE`(모듈 상수)로 분리해 회귀 테스트가 문구를 검증하게 한다.

```text
당신은 데이터 분석 결과를 **자연어 텍스트로만** 작성하는 분석가입니다.
차트·그래프·시각화의 "생성"은 당신의 역할이 아니며, 이후 별도의 시각화 노드가 전담합니다.

## 사용자 질문
{query}

## 엑셀 데이터
{excel_data}

## 웹 검색 결과
{web_context or "없음"}

## 분석 지침 (반드시 준수)
1. 제공된 엑셀/웹 데이터에 **실제로 존재하는 값**만 사용한다.
   데이터에 없으면 "데이터에 없음"이라고 명시하고, 추측·예측·창작하지 않는다.
2. 질문이 **요청한 범위만** 답한다. 묻지 않은 추가 분석·추천·전망·총평은 덧붙이지 않는다.
3. 답변은 **한국어 자연어 문장**으로만 작성한다.

## 출력 형식 — 엄격 제한
- 다음은 **절대 출력 금지**: 코드블록(```), JSON, 차트/그래프 스펙,
  Chart.js·matplotlib 등 시각화 코드, base64/이미지 데이터.
- 사용자가 "그래프로 그려줘 / 차트로 보여줘"라고 해도 **차트를 직접 만들지 않는다.**
  대신 차트로 표현될 **항목별 수치를 자연어로 나열**한다.
  예) "사용자별 남은 휴가 — 배상규 5일, 김철수 3일, 이영희 7일"
  실제 차트는 다음 단계(시각화 노드)가 이 수치를 바탕으로 생성한다.
- 따라서 당신의 출력은 항상 **"분석 텍스트 (+ 필요 시 항목별 수치 나열)"** 형태를 벗어나지 않는다.
```

설계 의도 매핑:
- "차트 생성은 당신 역할 아님 + 출력 금지 목록" → 분석 노드의 JSON 생성 차단(Problem 1·3 해소)
- "그래프 요청 시 항목별 수치를 자연어로 나열" → `chart_builder`가 쓸 원재료를 텍스트로 보존(차트 정상 동작 유지)
- "요청 범위만, 추측 금지" → 사용자 요구 "예상 범위를 안 넘어가게" 충족

### 4-3. AnalysisOutputSanitizer — 2차 방어선 (domain, 순수)

프롬프트만으로 LLM 일탈을 100% 막을 수 없으므로, 새어 나온 페이로드를 저장 전에 제거한다.

```python
# src/domain/visualization/analysis_output_policy.py
import re

class AnalysisOutputSanitizer:
    """분석 텍스트에서 시각화/코드 페이로드를 제거하는 순수 정책.

    chart_router/evaluate가 깨끗한 자연어만 받도록 보장한다.
    차트 생성은 chart_builder의 책임이므로, 분석 텍스트의 코드블록은
    하류에 불필요한 노이즈일 뿐이다.
    """

    _FENCE_RE = re.compile(r"```.*?```", re.DOTALL)   # ```json ... ```, ```python ... ```

    def strip(self, text: str) -> str:
        if not text:
            return text
        cleaned = self._FENCE_RE.sub("", text)
        return cleaned.strip()
```

- **순수 함수**(외부 의존 없음) → domain 적합, 단위 테스트 용이.
- 펜스 코드블록 제거를 우선 구현(가장 흔한 누수 형태). 펜스 없는 raw JSON 객체 제거는 오탐 위험이 있어 Design에서 정밀도 검토 후 선택 적용.
- 새니타이즈 발생 시 `logger.info`로 1줄 관측(프롬프트 일탈 빈도 모니터링용).

### 4-4. `_analyze_node` 적용 지점

```python
response = await self._claude.complete(claude_request)
response_text = self._output_sanitizer.strip(response.content)   # ← 추가
# 이후 search_decision/analysis_text 저장에 정제된 텍스트 사용
```

- 새니타이저는 워크플로우 생성자에서 주입(기본값 `AnalysisOutputSanitizer()`)하거나 모듈 상수로 보유. DI 일관성은 기존 생성자 패턴을 따른다(Design 확정).
- 흐름·반환 키는 불변 → 회귀 위험 최소.

---

## 5. 테스트 계획 (TDD)

### 5-1. 프롬프트 회귀 테스트 (application)
- `_build_analysis_prompt("...", {...}, "")` 결과 문자열에 핵심 제약 문구 포함 검증:
  - "자연어 텍스트로만" / "차트를 직접 만들지 않는다" / "코드블록" / "항목별 수치" / "요청한 범위만"
- query/excel_data/web_context가 본문에 치환되는지.

### 5-2. AnalysisOutputSanitizer 단위 테스트 (domain)
- ```` ```json {...} ```` 포함 텍스트 → 펜스 제거, 자연어 문장만 남음.
- ```` ```python ... ```` 포함 → 제거.
- 펜스 없는 일반 분석 텍스트 → 변형 없음(idempotent).
- 빈 문자열/None → 안전 반환.

### 5-3. `_analyze_node` 통합 테스트 (application, FakeClaude)
- FakeClaude가 "분석 텍스트 + ```json 차트```" 반환 → 저장된 `analysis_text`에 ``` 펜스 없음.
- 정제 후 텍스트가 `chart_router` 휴리스틱에 들어갔을 때 인라인 JSON 숫자로 인한 오탐이 사라짐(수치 텍스트는 보존).
- 정상 텍스트 입력 → 기존 동작 보존(회귀 없음).

> 모든 신규/변경은 **RED → GREEN** (CLAUDE.md TDD 필수). Windows 이벤트 루프 플레이키 이슈는 격리 실행으로 검증.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| 프롬프트 본문 변경 | 분석 답변 톤/형식이 더 엄격해짐 | 사용자 의도(범위 고정)와 일치 |
| 새니타이저 적용 | `analysis_text`에서 코드블록 제거 | 차트는 어차피 `chart_builder`가 생성 → 정보 손실 없음 |
| 그래프 구조 | **불변** (노드/엣지 추가 없음) | 회귀 위험 낮음 |
| 응답 스키마 | **불변** | `/api-contract-sync` 불필요, 프론트 변경 없음 |
| 토큰 비용 | 프롬프트 길이 소폭 증가 | 무시 가능, 일탈/retry 감소로 상쇄 가능 |
| supervisor analysis 노드 | 미반영(후속) | 동일 약한 프롬프트 잔존 — §7 후속 Task |

---

## 7. 구현 순서

1. `tests/domain/visualization/test_analysis_output_policy.py` 작성(RED) → `AnalysisOutputSanitizer` 구현(GREEN) — 5-2
2. 프롬프트 회귀 테스트 작성(RED) → `_ANALYSIS_GUIDE` 상수화 + `_build_analysis_prompt` 교체(GREEN) — 5-1
3. `_analyze_node`에 새니타이저 주입·적용 + 통합 테스트 — 5-3
4. 전체 테스트 격리 실행으로 그린 확인
5. `/pdca analyze analyze_with_claude` (Gap 분석) → Report
6. (후속 Task) `workflow_compiler.py:645` supervisor analysis 노드에 동일 가이드/새니타이저 재사용

---

## 8. 미해결 / 후속 이슈 (Design에서 확정)

- **raw JSON(펜스 없음) 제거 여부**: 정상 분석 텍스트의 중괄호/숫자를 오탐할 위험 → Design에서 정밀 정규식 또는 미적용 결정.
- **새니타이저 주입 방식**: 워크플로우 생성자 DI vs 모듈 상수 — 기존 DI 패턴과의 일관성 확인.
- **supervisor analysis 노드 통합 범위**: 동일 상수/정책을 공용화할지(`domain/visualization`에 프롬프트 가이드 상수 공유) Design에서 결정.
- **그래프 요청 거부 톤**: "차트는 다음 단계가 그린다"를 사용자에게 노출할지, 내부 지침으로만 둘지(답변 UX) 확정.
