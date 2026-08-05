# eval-hub Gap Analysis (Check)

> **Feature**: eval-hub — 평가 허브 4탭 (데이터셋/평가 실행/평가기/대시보드)
> **분석일**: 2026-08-03
> **기준**: `docs/02-design/features/eval-hub.design.md`
> **분석 방법**: gap-detector 에이전트 (Design §2.1~2.5, §3.1~3.6 → 101개 검증 항목) + 지적 갭 즉시 수정 후 재검증

---

## Match Rate

| 시점 | Match Rate | 비고 |
|------|:---------:|------|
| 1차 분석 (gap-detector) | 91.1% (92/101) | High 1 · Medium 4 · Low 4 |
| **갭 수정 후 (최종)** | **98.0% (99/101)** | 잔여 2건은 Low 스코프 축소로 기록 |

| Category | 1차 | 최종 |
|----------|:---:|:---:|
| 백엔드 (§2.1~2.5, 47항목) | 95.7% | 100% |
| 프론트 (§3.1~3.6, 54항목) | 87.0% | 96.3% |
| Architecture (Thin DDD) | 100% | 100% |

---

## 1차 분석 발견 갭과 조치 결과

| # | 심각도 | 내용 | 조치 |
|---|:------:|------|------|
| G-01 | **High** | `queryKeys.ts`에 `eval` 키 중복 선언 — eval-hub 블록이 agent-eval-gate의 `feedback/agents/recentNegative` 키를 덮어써 답변 피드백 기능 런타임 크래시 (기존 기능 회귀) | ✅ **수정** — 두 블록을 단일 `eval` 네임스페이스로 병합. `MessageFeedback.test.tsx` 9건 + tsc로 회귀 확인 |
| G-02 | Medium | failed run "동일 조건 재실행" 버튼 미구현 (BackgroundTasks 유실 리스크 완화책) | ✅ **수정** — `RunDetailPanel`에 재실행 버튼, `run.config`→`CreateRunModal` prefill 주입 |
| G-03 | Medium | 실행 폼 `sample_ratio` 입력 누락 (항상 1.0) | ✅ **수정** — 폼 필드 + 0<x≤1 인라인 검증 |
| G-04 | Medium | 문서→QA 생성 파일 크기 상한 없음 | ✅ **수정** — `eval_qa_gen_max_file_mb`(기본 15) 설정 신설, 파싱 전 차단 + 테스트 |
| G-05 | Medium | 생성 LLM 실패가 500으로 전파 (원인 은닉) | ✅ **수정** — 라우터에서 502 + detail 원인 표면화 |
| G-06 | Low | 대시보드 `target_type_counts` 미표시 | ✅ **수정** — 대상 유형 분포 칩 추가 |
| G-07 | Low | 대시보드 recent_runs 클릭 → 실행 상세 이동 | ⏸ **스코프 축소** — run 상세 선택 상태가 RunsTab 로컬이라 딥링크 배관 필요. 후속(대시보드 고도화)으로 이월 |
| G-08 | Low | EvaluatorsTab/DashboardTab 개별 테스트 파일 부재 | ⏸ **스코프 축소** — `index.test.tsx`가 렌더·admin 가시성·데이터 표시를 커버(부분 충족). 개별 파일 분리는 후속 |
| G-09 | Low | 파일 업로드 성공→목록 갱신 테스트 미커버 | ✅ **수정** — multipart 전송·invalidate 재조회 테스트 추가 |

## 설계와 다르게 구현 (동작 동등 — 구현이 진실, 문서 갱신 대상)

- DOCX 추출: `python-docx`(미설치) → 표준 라이브러리 `zipfile+ElementTree`
- XLSX 파싱: `pandas_excel_parser` 재사용 → `pandas.read_excel` 직접 호출
- admin 판별: `useAuth` → `useAuthStore` / KB 선택: `useCollections` → `useKnowledgeBases`
- 백엔드 테스트 파일 분할 → `test_ragas_testset_endpoints.py` 등으로 통합 (커버리지 동등)
- mutation 무효화: 개별 키 → `queryKeys.eval.all` 일괄

## 설계에 없는 추가 구현 (사전 공지 편차 — 확인 완료)

1. **배치 평가 실제 실행 계층**: 기존 코드는 run 등록 후 영원히 pending인 구조 → `BatchEvalExecutor`(create_task 싱글턴+run 조회 재시도) + `SessionScopedEvalRunStore`(D11 독립 세션) + `DefaultTargetExecutor`(rag=검색+LLM답변 / retrieval=검색+순위메트릭 / agent=`RunAgentUseCase` 헤드리스, agent-schedule §6.2 공유) 신설
2. **agent 대상 메트릭 3종 제한**: 컨텍스트가 없어 faithfulness 계산 불가 — `TARGET_METRICS` SoT에서 제외, 카탈로그·실행 검증 공유

## 테스트 결과 (최종)

- 백엔드: ragas 계열 76건 전체 통과 (application 55 + api 23 중복 제외 집계), V055 DDL COMMENT 검사 통과
- 프론트: EvalDatasetPage 14건 + MessageFeedback 회귀 9건 + 레이아웃 31건 통과, tsc 클린
- verify-architecture: eval-hub 신규 코드 위반 0 (기존 파일 위반 5건은 무관)

## 미검증 이월 (정적 분석 범위 밖)

- V055 실제 DB 적용 + venv 서버 기동 E2E: 테스트셋 생성 3종 → 배치 실행 → 폴링 → 점수 확인, 일반계정 타인 404 / admin 전체 열람
- RAGAS 실평가·QA 생성은 OpenAI 키 필요 (LLM 호출 실측 미수행)
- `openpyxl` venv 미설치 표류 발견·설치함 — 배포 환경 동일 여부 확인 필요

## 결론

Match Rate 98.0% (≥90%) — **Report 단계 진행 가능**. 잔여 2건(G-07/G-08)은 Low이며 후속 이월로 기록.
