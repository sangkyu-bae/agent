# ANALYZE_WITH_CLAUDE: Gap 분석 (Check)

> 상태: Check
> 연관 Design: `docs/02-design/features/analyze_with_claude.design.md`
> 연관 Task: ANALYZE-PROMPT-001
> 분석일: 2026-06-09
> 분석 도구: gap-detector (read-only)

---

## 종합 점수

| 항목 | 점수 | 상태 |
|------|:----:|:----:|
| Design 일치도 | 100% | ✅ |
| 아키텍처 준수 (CLAUDE.md 레이어) | 100% | ✅ |
| 컨벤션 준수 | 100% | ✅ |
| **Match Rate** | **100%** | ✅ |

테스트: 새니타이저 11 + 가이드 6 + excel 16(통합 2 추가) + compiler 28 = **전부 통과**.

---

## Design 결정 4건 검증 (Design §0)

| # | 결정 | 구현 위치 | 상태 |
|---|------|-----------|:----:|
| 1 | JSON 제거: 펜스 + 균형 중괄호 객체 + 객체 배열 제거, 수치 배열 보존 | `analysis_output_policy.py` `_FENCE_RE` / `_strip_json_objects`(`_JSON_KEY_RE` 게이트) / `_strip_json_arrays`(`"{" in b` 게이트) | ✅ |
| 2 | 모듈 상수(DI 아님) `ANALYSIS_OUTPUT_SANITIZER` | `analysis_output_policy.py` 모듈 싱글톤, 양쪽 노드에서 모듈 레벨 import | ✅ |
| 3 | 공용화: excel + supervisor 양쪽 적용 | excel `excel_analysis_workflow.py` `_build_analysis_prompt`/`_analyze_node`; supervisor `workflow_compiler.py` `_analyze_context` | ✅ |
| 4 | 파이프라인 메타설명 답변 노출 금지 | `analysis_prompt.py` 가이드 "메타 설명을 답변에 쓰지 않는다" + 회귀 테스트 `test_analysis_prompt.py::test_no_meta_exposure` | ✅ |

---

## 컴포넌트별 일치

| Design 항목 | 구현 | 상태 |
|-------------|------|:----:|
| `AnalysisOutputSanitizer` (domain, 순수 regex) | `analysis_output_policy.py` | ✅ |
| `strip()` 3단계: 펜스 → 객체/배열 | 존재 (**배열 먼저 → 객체**, 잔여물 방지) | ✅ (의도된 순서) |
| `ANALYSIS_OUTPUT_SANITIZER` 싱글톤 | 존재 | ✅ |
| `ANALYSIS_OUTPUT_GUIDE` 상수 (6개 핵심 문구) | `analysis_prompt.py` 전부 포함 | ✅ |
| excel `_build_analysis_prompt` 가이드 사용 | 적용 | ✅ |
| excel `_analyze_node` 저장 전 새니타이즈 | 적용 | ✅ |
| supervisor `_analyze_context` 가이드 + 새니타이즈 | 적용 | ✅ |
| 그래프/노드/엣지/응답 스키마 불변 | 무변경 확인 | ✅ |

---

## 차이점 (Differences)

### 🔴 미구현 (Design O, Impl X)
없음.

### 🟡 의도된 편차 (Design 허용 범위)

| 항목 | Design | 구현 | 영향 |
|------|--------|------|------|
| `strip()` 단계 순서 | §3-1 코드 예시: 객체 → 배열 | **배열 → 객체** (코드 주석 "잔여물 방지") | 없음 — 객체 배열 `[{...}]`에서 잔여 `[,]` 방지. Design 산문은 순서를 강제하지 않음 |
| 헬퍼 분리 | §3-1 인라인 `while j` 스캔 | `_match_close` 보조 함수 분리 | 없음 — Design §8이 명시 허용("길이 점검 시 보조 함수 분리"), 40줄 규칙 준수 |

### 🔵 변경 (Design ≠ Impl)
없음.

---

## 아키텍처 준수 (CLAUDE.md)

- domain `analysis_output_policy.py`: 순수 `re`만 사용, LangChain/외부/DB 미참조 ✅
- application → domain 정방향 참조, domain → application 없음 ✅
- 프롬프트 텍스트 자산을 application에 배치 ✅
- `_strip_balanced`/`_match_close`: 단일 루프, if 중첩 ≤2, 40줄 미만 ✅

---

## 후속 권장 (선택, backlog)

1. supervisor `_analyze_context` 통합 테스트 추가 (Design §5-4, 선택 표기) — excel과 대칭 커버리지.
2. Design §3-1 코드 샘플을 배열-우선 순서로 동기화 (문서-구현 일치).

---

## 결론

Match Rate **100%** — Design의 모든 컴포넌트·결정 4건·필수 테스트(5-1·5-2·5-3)가 구현·검증됨. 2건의 편차는 Design §8이 허용한 의도적 개선이며 코드에 문서화됨. bkit 임계(≥90%) 충족 → `/pdca report analyze_with_claude` 진행 가능.
