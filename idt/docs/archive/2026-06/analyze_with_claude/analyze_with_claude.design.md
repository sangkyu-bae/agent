# ANALYZE_WITH_CLAUDE: Design — 분석 프롬프트 엄격화 + 출력 새니타이즈 (공용)

> 상태: Design
> 연관 Plan: `docs/01-plan/features/analyze_with_claude.plan.md`
> 연관 Task: ANALYZE-PROMPT-001
> 작성일: 2026-06-09
> 우선순위: High

---

## 0. 결정 반영 (Plan §8 미해결 이슈 확정)

| # | Plan 미해결 이슈 | 결정 | 본 설계 반영 |
|---|------------------|------|--------------|
| 1 | raw JSON(펜스 없음) 제거 여부 | **제거한다** | 새니타이저가 펜스 블록 + 균형 중괄호/대괄호 JSON 객체까지 제거 (§3-1) |
| 2 | 새니타이저 주입 방식 (DI vs 상수) | **모듈 상수** | 모듈 레벨 싱글톤 `ANALYSIS_OUTPUT_SANITIZER` import 사용, 생성자 DI 없음 (§3-1, §3-3) |
| 3 | supervisor analysis 노드 통합 범위 | **공용화** | 프롬프트 가이드 상수 + 새니타이저를 excel·supervisor 양쪽에서 재사용 (§3-2, §3-4) |
| 4 | "차트는 다음 단계가 그린다" UX 노출 | **노출하지 않는다** | 프롬프트가 파이프라인/시각화 메타 설명을 답변에 쓰지 못하게 금지 (§3-2) |

---

## 1. 설계 개요 (Overview)

분석 노드의 책임을 **"수치가 담긴 자연어 텍스트 생성"** 으로 고정한다. 두 개의 산출물:

1. **`ANALYSIS_OUTPUT_GUIDE`** (application 모듈 상수) — 출력 형식·범위·금지사항을 못박는 공용 프롬프트 블록.
2. **`AnalysisOutputSanitizer`** (domain 순수 정책) + 모듈 싱글톤 `ANALYSIS_OUTPUT_SANITIZER` — 프롬프트를 어기고 새어 나온 코드블록/JSON을 저장 전 제거하는 2차 방어선.

이 둘을 **excel 분석 노드**와 **supervisor analysis 노드** 양쪽에 적용한다(공용화). 그래프 구조·노드·엣지·응답 스키마는 불변.

```
┌──────────────────────────────────────────────────────────────┐
│ ANALYSIS_OUTPUT_GUIDE (application/visualization/analysis_prompt.py) │
│   ├─ excel_analysis_workflow._build_analysis_prompt           │
│   └─ workflow_compiler._analyze_context                       │
│ ANALYSIS_OUTPUT_SANITIZER (domain/visualization/...)          │
│   ├─ excel _analyze_node   : response.content → strip → 저장   │
│   └─ supervisor _analyze_context : response.content → strip   │
└──────────────────────────────────────────────────────────────┘
                          │ analysis_text (clean)
                          ▼
        chart_router ──visualize──▶ chart_builder (차트의 유일 소유자)
```

---

## 2. 모듈 구성 (Files)

| 파일 | 신규/변경 | 레이어 | 내용 |
|------|-----------|--------|------|
| `src/domain/visualization/analysis_output_policy.py` | 신규 | domain | `AnalysisOutputSanitizer` 클래스 + 모듈 싱글톤 `ANALYSIS_OUTPUT_SANITIZER` |
| `src/application/visualization/analysis_prompt.py` | 신규 | application | `ANALYSIS_OUTPUT_GUIDE` 상수 (공용 프롬프트 블록) |
| `src/application/workflows/excel_analysis_workflow.py` | 변경 | application | `_build_analysis_prompt` 가이드 사용 + `_analyze_node` 새니타이즈 적용 |
| `src/application/agent_builder/workflow_compiler.py` | 변경 | application | `_analyze_context` 가이드 사용 + 응답 새니타이즈 적용 |
| `tests/domain/visualization/test_analysis_output_policy.py` | 신규 | - | 새니타이저 단위 테스트 |
| `tests/application/visualization/test_analysis_prompt.py` | 신규 | - | 가이드 상수 문구 회귀 테스트 |
| `tests/application/test_excel_analysis_workflow.py` | 변경 | - | `_analyze_node` 새니타이즈 통합 테스트 추가 |

> 레이어 근거: 새니타이즈는 외부 의존 없는 **순수 규칙** → domain. 프롬프트 가이드는 LLM 호출 흐름에 쓰는 **application 텍스트 자산**으로, domain이 프롬프트를 보유하지 않도록 application에 둔다. (CLAUDE.md §2: domain은 LangChain/외부 미사용)

---

## 3. 상세 설계 (Detailed Design)

### 3-1. `AnalysisOutputSanitizer` (domain, 순수)

**결정 1·2 반영**: 펜스 + raw JSON 제거, 모듈 싱글톤.

```python
# src/domain/visualization/analysis_output_policy.py
import re


class AnalysisOutputSanitizer:
    """분석 텍스트에서 코드블록/JSON 페이로드를 제거하는 순수 정책.

    chart_router(숫자 토큰 휴리스틱)·evaluate_hallucination(자연어 평가)가
    깨끗한 자연어만 받도록 보장한다. 차트 JSON 생성은 chart_builder의 책임이므로,
    분석 텍스트의 코드/JSON은 하류에 노이즈일 뿐이다.
    """

    _FENCE_RE = re.compile(r"```.*?```", re.DOTALL)        # ```json ... ```, ```python ... ```
    _JSON_KEY_RE = re.compile(r'"[^"]+"\s*:')              # "type": 같은 JSON 키 신호

    def strip(self, text: str) -> str:
        if not text:
            return text
        cleaned = self._FENCE_RE.sub("", text)             # 1) 펜스 코드블록 제거
        cleaned = self._strip_json_objects(cleaned)        # 2) 균형 {…} 객체 제거
        cleaned = self._strip_json_arrays(cleaned)         # 3) 객체 포함 […] 배열 제거
        return cleaned.strip()

    def _strip_json_objects(self, text: str) -> str:
        return self._strip_balanced(
            text, "{", "}", predicate=lambda b: bool(self._JSON_KEY_RE.search(b))
        )

    def _strip_json_arrays(self, text: str) -> str:
        return self._strip_balanced(
            text, "[", "]", predicate=lambda b: "{" in b
        )

    @staticmethod
    def _strip_balanced(text, open_ch, close_ch, predicate) -> str:
        """open_ch..close_ch로 균형 잡힌 블록 중 predicate를 만족하는 것만 제거.

        정규식만으로는 중첩 괄호를 못 다루므로 깊이 스캔으로 균형 블록을 찾는다.
        닫힘을 못 찾거나 predicate 불만족이면 원문을 보존한다(오탐 방지).
        """
        out, i, n = [], 0, len(text)
        while i < n:
            if text[i] == open_ch:
                depth, j = 0, i
                while j < n:
                    if text[j] == open_ch:
                        depth += 1
                    elif text[j] == close_ch:
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                if j < n and predicate(text[i:j + 1]):
                    i = j + 1          # 블록 버림
                    continue
            out.append(text[i])
            i += 1
        return "".join(out)


# 결정 2: DI 아님 — 모듈 싱글톤으로 공용.
ANALYSIS_OUTPUT_SANITIZER = AnalysisOutputSanitizer()
```

**오탐(false-positive) 방어**:
- 객체 제거는 `"key":` 형태의 JSON 키 신호가 있을 때만. 한국어 산문에 `"단어":` 패턴은 사실상 없음.
- 닫는 괄호를 못 찾으면(불균형) 원문 보존 → 정상 문장의 단독 `{`/`[` 안전.
- 배열은 내부에 `{`가 있을 때만(객체 배열) 제거 → `[1, 2, 3]` 같은 수치 나열은 보존(차트 원재료 보호).

### 3-2. `ANALYSIS_OUTPUT_GUIDE` (application 상수)

**결정 4 반영**: 파이프라인/시각화 "다음 단계" 같은 메타 설명을 답변에 쓰지 못하게 한다.

```python
# src/application/visualization/analysis_prompt.py
"""분석 노드 공용 출력 가이드. excel·supervisor 분석 노드가 함께 사용한다."""

ANALYSIS_OUTPUT_GUIDE = """## 출력 형식 — 엄격 제한
- 답변은 **한국어 자연어 문장**으로만 작성한다.
- 다음은 **절대 출력 금지**: 코드블록(```), JSON, 차트/그래프 스펙,
  Chart.js·matplotlib 등 시각화 코드, base64/이미지 데이터.
- 사용자가 "그래프로 그려줘 / 차트로 보여줘"라고 해도 **차트를 직접 만들지 않는다.**
  대신 차트로 표현될 **항목별 수치를 자연어로 나열**한다.
  예) "사용자별 남은 휴가 — 배상규 5일, 김철수 3일, 이영희 7일"
- 시각화 처리 방식·내부 단계·"다음 단계에서 그려진다" 같은 **메타 설명을 답변에 쓰지 않는다.**
  요청에 대한 분석과 수치만 제시한다.

## 분석 지침 (반드시 준수)
1. 제공된 데이터에 **실제로 존재하는 값**만 사용한다.
   없으면 "데이터에 없음"이라고 명시하고, 추측·예측·창작하지 않는다.
2. 질문이 **요청한 범위만** 답한다. 묻지 않은 추가 분석·추천·전망·총평을 덧붙이지 않는다."""
```

핵심: "항목별 수치 나열"은 유지(→ `chart_builder`가 막대그래프 생성 가능). "메타 설명 금지"로 결정 4 충족.

### 3-3. excel `_analyze_node` / `_build_analysis_prompt` 변경

```python
# excel_analysis_workflow.py 상단
from src.application.visualization.analysis_prompt import ANALYSIS_OUTPUT_GUIDE
from src.domain.visualization.analysis_output_policy import ANALYSIS_OUTPUT_SANITIZER

# _build_analysis_prompt 교체
def _build_analysis_prompt(self, query, excel_data, web_context) -> str:
    return f"""당신은 데이터 분석 결과를 자연어 텍스트로만 작성하는 분석가입니다.
차트·그래프·시각화의 "생성"은 당신의 역할이 아닙니다.

## 사용자 질문
{query}

## 엑셀 데이터
{excel_data}

## 웹 검색 결과
{web_context if web_context else "없음"}

{ANALYSIS_OUTPUT_GUIDE}"""

# _analyze_node: 저장 전 새니타이즈 (line 191~192 부근)
response = await self._claude.complete(claude_request)
response_text = ANALYSIS_OUTPUT_SANITIZER.strip(response.content)   # ← 추가
```

이후 `search_decision.decide(...)`·`analysis_text` 저장에 정제된 `response_text` 사용. 반환 키·흐름 불변.

### 3-4. supervisor `_analyze_context` 변경 (공용화)

```python
# workflow_compiler.py 상단 import 추가
from src.application.visualization.analysis_prompt import ANALYSIS_OUTPUT_GUIDE
from src.domain.visualization.analysis_output_policy import ANALYSIS_OUTPUT_SANITIZER

# _analyze_context (line 643~652) 교체
analysis_prompt = (
    f"{system_prompt}\n\n"
    f"당신은 데이터 분석가입니다. {source_hint} 사용자의 질문에 답합니다.\n\n"
    f"{ANALYSIS_OUTPUT_GUIDE}\n\n"
    f"[분석 대상 데이터]\n{context}\n\n[질문]\n{question}"
)
response = await llm.ainvoke(
    [{"role": "system", "content": analysis_prompt}, *conversation]
)
content = response.content if hasattr(response, "content") else str(response)
return ANALYSIS_OUTPUT_SANITIZER.strip(content)   # ← 새니타이즈 적용
```

기존의 약한 문구("분석한 결과만 간결히 반환…")를 공용 가이드로 대체 → 두 노드의 출력 규칙이 일치.

---

## 4. 시퀀스 (그래프 요청 케이스)

```
사용자: "배상규 남은 휴가 알려주고 사용자별 남은 휴가 그래프로 그려줘"
  │
  ▼ analyze_with_claude (_analyze_node)
  │   프롬프트: ANALYSIS_OUTPUT_GUIDE 적용 → 차트 생성 금지, 수치 나열 유도
  │   LLM 출력 예: "사용자별 남은 휴가 — 배상규 5일, 김철수 3일, 이영희 7일."
  │   (만약 LLM이 ```json{…}``` 섞으면) → ANALYSIS_OUTPUT_SANITIZER.strip() 제거
  │   analysis_text = 깨끗한 자연어 (수치 보존)
  ▼ evaluate_hallucination  : 자연어만 평가 → 정확
  ▼ chart_router            : explicit "그래프" 키워드 → visualize
  ▼ chart_builder           : analysis_text의 "배상규 5일…" → 막대 Chart.js config
  ▼ END                     : analysis_text + charts 응답
```

---

## 5. 테스트 설계 (TDD, RED→GREEN)

### 5-1. `test_analysis_output_policy.py` (domain 단위)
| 케이스 | 입력 | 기대 |
|--------|------|------|
| 펜스 json 제거 | `"배상규 5일.\n\`\`\`json\n{\"a\":1}\n\`\`\`"` | 펜스 사라지고 `"배상규 5일."` |
| 펜스 python 제거 | `"...\n\`\`\`python\nx=1\n\`\`\`"` | 코드 제거 |
| raw 객체 제거 | `'결과: {"type":"bar","data":[1,2]}'` | `"결과:"` (객체 제거) |
| 객체 배열 제거 | `'[{"x":1},{"x":2}] 추세'` | `"추세"` |
| 수치 배열 보존 | `"값은 [1, 2, 3] 입니다"` | **변형 없음** (차트 원재료 보호) |
| 일반 산문 보존 | `"배상규 5일, 김철수 3일"` | **변형 없음** (idempotent) |
| 불균형 괄호 보존 | `"수식 { 미완성"` | **변형 없음** |
| 빈/None | `""`, `None` | 안전 반환 |

### 5-2. `test_analysis_prompt.py` (가이드 회귀)
- `ANALYSIS_OUTPUT_GUIDE`에 핵심 문구 포함: "자연어 문장으로만", "절대 출력 금지", "차트를 직접 만들지 않는다", "항목별 수치를 자연어로 나열", "메타 설명을 답변에 쓰지 않는다", "요청한 범위만".

### 5-3. excel `_analyze_node` 통합 (FakeClaude)
- FakeClaude가 `"배상규 5일.\n\`\`\`json\n{\"type\":\"bar\"}\n\`\`\`"` 반환 → 저장된 `analysis_text`에 ``` 펜스·`"type"` 없음, `"배상규 5일."` 보존.
- 정상 텍스트 → 기존 동작 보존(회귀 없음).
- `_build_analysis_prompt` 결과에 `ANALYSIS_OUTPUT_GUIDE`가 포함되는지.

### 5-4. supervisor `_analyze_context` (선택, FakeLLM)
- 응답에 펜스 JSON 섞임 → 반환 문자열 정제 확인.

> Windows 이벤트 루프 플레이키: 통합 테스트는 격리 실행으로 검증.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 완화 |
|------|------|------|
| 두 분석 노드 프롬프트 변경 | 답변 형식 엄격화 | 사용자 의도(범위 고정)와 일치 |
| 새니타이즈 오탐 | 정상 JSON-like 텍스트 제거 위험 | 키 신호/균형 괄호 조건 + 수치 배열 보존 + 테스트 5-1 |
| 그래프 구조 | **불변** | 노드/엣지 무변경 |
| 응답 스키마 | **불변** | 프론트 무관, `/api-contract-sync` 불필요 |
| 공용 모듈 추가 | import 2곳 추가 | 단일 책임, 순환 의존 없음(domain←application 방향 유지) |

---

## 7. 구현 순서

1. `test_analysis_output_policy.py`(RED) → `analysis_output_policy.py` 구현(GREEN) — 5-1
2. `test_analysis_prompt.py`(RED) → `analysis_prompt.py` `ANALYSIS_OUTPUT_GUIDE` 작성(GREEN) — 5-2
3. excel `_build_analysis_prompt`/`_analyze_node` 변경 + 통합 테스트 — 5-3
4. supervisor `_analyze_context` 변경(공용화) + 테스트 — 5-4
5. 전체 테스트 격리 실행 그린 확인
6. `/pdca analyze analyze_with_claude` (Gap 분석) → Report

---

## 8. 레이어 규칙 점검 (CLAUDE.md)

- domain(`analysis_output_policy`)은 외부/LangChain 미사용 ✓ (순수 regex)
- application이 domain을 참조(정방향) ✓ / domain→application 참조 없음 ✓
- 프롬프트 텍스트 자산은 application에 위치 ✓
- 함수 40줄·if 2단계 제약: `_strip_balanced`는 루프 1개+분기 → 준수, 길이 점검 필요 시 보조 함수 분리
