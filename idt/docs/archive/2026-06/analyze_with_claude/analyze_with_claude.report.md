# ANALYZE_WITH_CLAUDE: 완료 보고서 (PDCA Report)

> 상태: Completed
> 연관 Task: ANALYZE-PROMPT-001
> 작성일: 2026-06-09
> Match Rate: 100%

---

## 1. Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | analyze_with_claude (분석 노드 프롬프트 엄격화 + 차트 책임 분리) |
| 기간 | 2026-06-09 (Plan→Design→Do→Check→Report 단일 세션) |
| 레벨 | Dynamic (FastAPI + LangGraph 백엔드) |
| Match Rate | 100% (gap-detector) |
| 테스트 | 새니타이저 11 + 가이드 6 + excel 16 + compiler 28 = 전부 통과 |

### 1.2 PDCA 진행

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ 100% → [Report] ✅
```

### 1.3 Value Delivered (4관점)

| 관점 | 전달된 가치 | 지표 |
|------|-------------|------|
| **Problem** | 분석 노드가 분석 텍스트와 차트 JSON을 함께 뱉어 하류(할루시네이션 평가·차트 라우팅)를 오염시키던 문제 제거 | 누수 JSON → `analysis_text`에서 0건 (새니타이즈 검증) |
| **Solution** | "분석은 텍스트, 차트는 chart_builder"를 프롬프트(`ANALYSIS_OUTPUT_GUIDE`) + 도메인 정책(`AnalysisOutputSanitizer`)으로 이중 강제. excel·supervisor 양쪽 공용화 | 신규 2파일 + 변경 2파일, 그래프 구조 무변경 |
| **Function UX Effect** | 그래프 요청 시 분석 노드는 "배상규 5일, 김철수 3일…" 수치만 자연어로 제시 → chart_builder가 정상 경로로 차트 생성. 묻지 않은 추측·전망 차단 | 차트는 `chart_router→chart_builder` 단일 경로로만 생성 |
| **Core Value** | 그래프 설계 의도를 코드로 못박아 예측 가능성·파이프라인 정확도 확보. 응답 스키마 불변으로 프론트 영향 0 | CLAUDE.md 레이어/컨벤션 100% 준수 |

---

## 2. 구현 산출물

### 2.1 신규 파일

| 파일 | 레이어 | 책임 |
|------|--------|------|
| `src/domain/visualization/analysis_output_policy.py` | domain | `AnalysisOutputSanitizer`(펜스+raw JSON 균형괄호 제거, 수치배열 보존) + 모듈 싱글톤 `ANALYSIS_OUTPUT_SANITIZER` |
| `src/application/visualization/analysis_prompt.py` | application | 공용 `ANALYSIS_OUTPUT_GUIDE` 상수 (출력 형식·범위 제약) |

### 2.2 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/application/workflows/excel_analysis_workflow.py` | `_build_analysis_prompt`에 가이드 적용, `_analyze_node`에서 응답 새니타이즈 후 저장 |
| `src/application/agent_builder/workflow_compiler.py` | supervisor `_analyze_context` 약한 프롬프트를 공용 가이드로 교체 + 응답 새니타이즈 (공용화) |

### 2.3 테스트 파일

| 파일 | 케이스 |
|------|--------|
| `tests/domain/visualization/test_analysis_output_policy.py` | 11 (펜스/raw 객체/객체배열 제거 + 수치배열·불균형 보존 + idempotent + edge) |
| `tests/application/visualization/test_analysis_prompt.py` | 6 (가이드 핵심 문구 회귀 방지) |
| `tests/application/test_excel_analysis_workflow.py` | +2 (`_analyze_node` 새니타이즈 통합, 프롬프트 가이드 포함) |

---

## 3. Design 결정 4건 반영 결과

| # | 결정 | 결과 |
|---|------|:----:|
| 1 | JSON 제거 (펜스+객체+객체배열, 수치배열 보존) | ✅ |
| 2 | 모듈 상수 `ANALYSIS_OUTPUT_SANITIZER` (DI 아님) | ✅ |
| 3 | 공용화 (excel + supervisor) | ✅ |
| 4 | 파이프라인 메타설명 답변 노출 금지 | ✅ |

---

## 4. 핵심 동작 검증

입력: `"사용자별 남은 휴가 — 배상규 5일.\n\`\`\`json\n{\"type\":\"bar\"}\n\`\`\`"`
→ 저장된 `analysis_text`: `"사용자별 남은 휴가 — 배상규 5일."` (JSON 제거, 수치 보존)
→ `chart_router`가 "그래프" 키워드로 visualize → `chart_builder`가 막대그래프 생성.

---

## 5. 영향 범위

| 항목 | 영향 |
|------|------|
| 그래프 구조 | 불변 (노드/엣지 무변경) |
| 응답 스키마 | 불변 (프론트 영향 0, `/api-contract-sync` 불필요) |
| 토큰 비용 | 프롬프트 길이 소폭 증가, 일탈/retry 감소로 상쇄 |
| 회귀 | compiler 28 + excel 16 전부 통과 — 회귀 없음 |

---

## 6. 후속 과제 (Backlog)

1. supervisor `_analyze_context` 통합 테스트 추가 (Design §5-4, 선택) — excel과 대칭 커버리지.
2. Design §3-1 코드 샘플을 배열-우선 순서로 동기화 (문서-구현 일치).
3. 새니타이즈 발생 빈도 로깅 모니터링 → 프롬프트 일탈 추세 관찰 (운영).

---

## 7. 학습 / 회고

- **잘된 점**: 기존 `chart_router→chart_builder` 경로를 그대로 두고, 프롬프트+순수 정책만으로 문제를 해결해 아키텍처 변경 없이 회귀 위험을 최소화.
- **개선점**: raw JSON 제거 시 오탐 방지를 위해 "키 신호 + 균형 괄호" 조건을 도입했고, 수치 배열 보존으로 차트 원재료를 지킴 — 이 균형이 핵심.
- **재사용 자산**: `ANALYSIS_OUTPUT_GUIDE` + `ANALYSIS_OUTPUT_SANITIZER`는 향후 신규 분석 노드에도 그대로 적용 가능한 공용 자산.
