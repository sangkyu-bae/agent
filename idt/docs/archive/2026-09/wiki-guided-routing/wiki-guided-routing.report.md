# wiki-guided-routing Completion Report

> **Feature**: wiki-guided-routing
> **Project**: sangplusbot / idt (백엔드)
> **Author**: 배상규
> **Date**: 2026-09-12
> **Status**: Completed (Match Rate 98%, Act 1회)
> **Docs**: [Plan](./wiki-guided-routing.plan.md) · [Design](./wiki-guided-routing.design.md) · [Analysis](./wiki-guided-routing.analysis.md)

---

## Executive Summary

### 1.1 Project Overview

에이전트 소유자가 위키에 "금리 정보는 fsb.or.kr 특정 페이지를 스크래핑하라"는 지침을 승인 등록했는데도, 채팅에서 수퍼바이저 LLM이 위키를 열람하지 않고 외부 수집 도구로 직행해 URL을 지어내고 실패 후 종료하던 문제를 고쳤다. 기존 "목차 → LLM 판단 → wiki_read" 설계는 유지하고, LLM이 판단할 수 있는 **신호**(목차 발췌·프레이밍·조건부 결정 규칙·결정적 실패 신호)를 보강했다.

| 항목 | 값 |
|------|----|
| 기간 | 2026-09-11 Plan → 2026-09-12 Report (2일) |
| 변경 | 소스 15파일 수정, 신규 소스 0, 테스트 신규 2 + 확장 10 (약 949줄 추가) |
| DB·API 계약 | 마이그레이션 0, 엔드포인트 변경 0, 프론트 무변경 |

### 1.2 Results Summary

| 지표 | 결과 |
|------|------|
| Match Rate | 초회 95% → Act-1 후 **98%** |
| Success Criteria | 6/6 |
| 회귀 | 전체 스위트 9043 passed / 58 failed — 기준선 대비 신규 실패 **0** (58건은 변경 전부터 존재) |
| 실런 재현 | 대상 에이전트 재실행 시 `supervisor → wiki_read_worker → scrape_url_worker(위키 URL 그대로)` |

### 1.3 Value Delivered

| Perspective | 계획 | 실제 |
|-------------|------|------|
| **Problem** | 위키 지침을 건너뛰고 URL 추측 | 실런 `538164a4`: iter=0에서 위키 열람("위키 목차에 전용 지침이 명시되어 있으므로 우선 열람"), 수집 URL = 위키 지침 URL. 변경 전 런 `8ccc097f`의 추측 URL·DNS 실패 재현 소멸 |
| **Solution** | 발췌+프레이밍+규칙+실패 폴백+Tool Guidelines 재생성 | D1~D5 전부 구현. 신규 소스 파일 0, state 필드 1개 추가, 메시지 규약 무변경 |
| **Function/UX Effect** | 위키로 경로 통제, 실패 시 되묻기 | 실런 `f7f41fe1`(위키 없는 에이전트, 존재하지 않는 도메인): 추측 URL 0건, "다른 URL을 추측해서 호출해서도 안 된다는 시스템 지침" 인용 후 사용자에게 대상 URL 되묻기 |
| **Core Value** | 코드 수정 없이 위키만으로 에이전트 통제, 일반화 | 문구·규칙 전부 도메인 중립. 금리 특화 하드코딩 0 |

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~07 구현 + 테스트 | ✅ | 신규 `test_tool_error_policy.py`(9), `test_supervisor_worker_error.py`(11) + 확장 10파일 |
| SC-2 | 재현 시 wiki_read → 수집 워커(fsb.or.kr) | ✅ | `ai_run_step`/`ai_tool_call` run `538164a4` |
| SC-3 | 위키 없는 에이전트 + 접속 불가 URL → 미추측·되묻기 | ✅ | run `f7f41fe1` |
| SC-4 | 도구 편집 후 Tool Guidelines 정합·타 섹션 보존 | ✅ | `test_d5_*` 6건 |
| SC-5 | FAILED 목록 diff 0 | ✅ | 3회 전체 실행(baseline/after/after2) 비교 |
| SC-6 | config 소비 지점 명기 | ✅ | `config.py` `wiki_toc_excerpt_chars` |

**Overall Success Rate**: 6/6

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 기존 설계 유지 + 신호 보강 (본문 통째 주입·강제 라우팅 기각) | ✅ | 강제 훅 없이도 iter=0 위키 라우팅 달성. 위키 미등록 에이전트 프롬프트 바이트 동일 |
| [Plan] | 실패 폴백 = FINISH+answer 되묻기 (인터럽트 없음) | ✅ | 상태 머신 추가 없이 실런 통과 |
| [Plan] | 발췌 방식: 목차 줄에 본문 앞부분 (사용자 결정, 통째 주입 대신) | ✅ | 120자 발췌에 URL까지 포함되어 수퍼바이저가 열람 결정 |
| [Design] | Option C 실용 균형 (state 필드 1 + 도메인 순수 함수 + 기존 렌더 패턴) | ✅ | 신규 소스 0, 교차 회귀 0 |
| [Design D1] | SQL SUBSTRING으로 본문 미조회 계약 유지 | ✅ (편차 1) | provider는 값이 0보다 클 때만 kwarg 전달 — 구 페이크 무회귀 위해 강화, Design 갱신 |
| [Design D4] | 결정적 감지 + LLM 판단 분리 | ✅ (한계 1) | soft 404(HTTP 200 + "404" 본문)는 미감지 — 의도된 범위로 문서화 |
| [Design D5] | 섹션 한정 교체, 사용자 편집 보존 | ✅ | 헤딩 없는 프롬프트 무변경 테스트 |

---

## 2. Related Documents

| 문서 | 경로 |
|------|------|
| Plan | `docs/01-plan/features/wiki-guided-routing.plan.md` |
| Design | `docs/02-design/features/wiki-guided-routing.design.md` (v0.1 + Check 반영 편집) |
| Analysis | `docs/03-analysis/wiki-guided-routing.analysis.md` (v0.2) |
| 참조 위키 | `docs/wiki/backend/patterns/supervisor-graph-contracts.md`, `docs/wiki/conventions/config-single-source-at-consumption.md`, `docs/wiki/conventions/false-green-quality-gates.md` |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 | 구현 위치 |
|----|----------|:----:|-----------|
| FR-01 | 목차 발췌(SQL 절단, config) | ✅ | `wiki_repository.py` `_toc_columns`, `schemas.py` `excerpt`, `toc_provider.py`, `config.py`, `main.py` |
| FR-02 | 렌더 시 발췌 꼬리·바이트 동일 | ✅ | `prompt_rendering.py` `_toc_line`, `_normalize_excerpt` |
| FR-03 | 프레이밍 문구 | ✅ | `_TOC_GUIDANCE_LINE`, `tool_registry.py`, `_WIKI_INSTRUCTION_VERBATIM` |
| FR-04 | 조건부 위키 우선 규칙 | ✅ | `workflow_compiler.py` `_render_wiki_guidance_block`, `supervisor_nodes.py` |
| FR-05 | 실패 신호 + 되묻기 블록 | ✅ | `ToolErrorPolicy`, `SupervisorState.last_worker_error`, `_wrap_worker`, `collect_pipeline.py` `_worker_error_of`, `_render_worker_error_block` |
| FR-06 | Tool Guidelines 섹션 재생성 | ✅ | `PromptAssemblyPolicy.replace_tool_section`, `update_agent_use_case.py` `_sync_tool_guidelines` |
| FR-07 | 재현 검증 | ✅ | 실런 2건(`538164a4`, `f7f41fe1`) |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|------|------|------|
| 토큰 | 목차 4000바이트 예산 내 | 첫 supervisor 호출 4109 → 4195 (+86 토큰, 위키 보유 에이전트) |
| 결정성 | 동일 입력 → 동일 출력 | `test_deterministic`, 발췌 바이트 동일 테스트 |
| 회귀 | FAILED diff 0 | ✅ |
| 성능 | 목차 본문 미조회 유지 | SUBSTRING만 추가, 추가 쿼리 0 |
| 계약 | tree API 불변 | 인프로세스 L1: 응답 키 불변, excerpt 미노출, 비인증 401 |
| 아키텍처 | 레이어 규칙 | 도메인 파일 외부 import 0, 신규 함수 전부 40줄 이내 |

### 3.3 Deliverables

- 소스: `src/` 15파일 (Design §12.1 목록), `## Design Ref` / `Plan SC` 주석 표기
- 테스트: 신규 2, 확장 10
- 문서: Plan / Design / Analysis / Report

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 사유 | 제안 |
|------|------|------|
| 표 추출 정확도 (`browser_extract` selector·페이지네이션, "검색" 클릭 후 데이터) | Plan에서 범위 밖. MCP 서버 소스가 이 워크스페이스에 없음. 실런에서 위키 URL 페이지가 "등록된 데이터가 없습니다"를 반환(검색 버튼 클릭 필요) | 별도 사이클. 단기 우회: 위키 지침에 "검색 버튼 클릭 후 추출"을 적으면 브라우저 워커 경로로 유도 가능 |
| soft 404 감지 | 설계 원칙("확실한 신호만") 밖 | 필요 시 `ToolErrorPolicy`에 본문 패턴 규칙 추가 검토 |
| `_rebuild_tool_workers` 59줄, `create_supervisor_node` 142줄 | 변경 전부터 40줄 초과 | 리팩토링 사이클 |
| 위키 미등록 에이전트 토큰 ±0 실측 | 동일 질문의 변경 전 런 부재 | 구조·단위 테스트로 증명 완료, 실측은 선택 |

### 4.2 Cancelled/On Hold Items

- 짧은 문서 본문 통째 주입 — Plan Checkpoint에서 기각(이중 경로)
- 결정적 강제 라우팅 — 계약 충돌로 기각

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 초회 | 최종 |
|----|:----:|:----:|
| Structural | 100% | 100% |
| Functional | 95% | 98% |
| Contract | 100% | 100% |
| Runtime | 90% | 97% |
| **Overall** | 95% | **98%** |

### 5.2 Resolved Issues

| ID | 심각도 | 처리 |
|----|:------:|------|
| G-01 | Important | 헬퍼 추출(`_sync_tool_guidelines`, `_toc_columns`) |
| G-02, G-05 | Minor | Design 문구 갱신 |
| G-03 | Minor | 런타임 시나리오 실런 통과 / 구조 증명 |
| G-04 | Minor | 알려진 한계 문서화 |
| G-06 (Check 중 발견) | Important | 목차 없으면 `wiki_worker_id=""` 게이트 + 테스트 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **DB 트레이스 기반 진단**: `ai_run_step.output_summary`(수퍼바이저 reasoning)와 `ai_tool_call.arguments_json`만으로 "기계적 결함이 아니라 LLM 판단 문제"임을 확정했고, 목차 블록을 직접 렌더해 사용자의 "이미 설계돼 있지 않나"라는 질문에 근거로 답할 수 있었다.
- **사용자 되묻기가 설계를 바꿨다**: 첫 제안(본문 통째 주입)은 사용자가 기존 설계 존재를 지적하면서 "목차 발췌"로 좁혀졌고, 결과적으로 스키마 변경 0·토큰 +86으로 해결됐다.
- **실런 검증을 Do에서 수행**: 첫 재현이 dev 서버 미반영으로 무효였음을 토큰 수 비교로 잡아냈고, TestClient 인프로세스 실행으로 즉시 재검증했다.
- **회귀는 FAILED 목록 diff**: 기준선 62 → 58(내 Red 4건 해소), 신규 0을 세 번 반복 확인.

### 6.2 What Needs Improvement (Problem)

- **bkit 서브에이전트 산출물 유실 2회**(Explore는 Write 없음, gap-detector는 transcript 0바이트). 분석을 메인이 직접 수행해 시간은 지켰지만 도구 신뢰도 문제는 남는다.
- **dev 서버 `--reload` 미반영**: uvicorn 프로세스 2개 공존. 실런 1회(`4829bde0`)가 변경 전 코드로 돌아 근거에서 제외했다.
- Bash heredoc Python으로 한글 문자열 치환 시 매칭 실패 1회 — Edit 도구로 전환.

### 6.3 What to Try Next (Try)

- 실런 전 "변경 반영 확인" 체크(예: 첫 supervisor 토큰 또는 버전 엔드포인트)를 절차화.
- gap-detector 대신 메인 세션 분석을 기본으로 하되, 구조·기능·계약·런타임 4축 체크리스트를 템플릿으로 고정.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- Design 단계에서 "런타임 시나리오에 필요한 픽스처(에이전트·위키 문서)"를 명시하면 Check가 빨라진다(이번엔 DB에서 즉석 탐색).
- Check 단계의 인라인 Act(사용자 "지금 모두 수정")는 작은 Gap에 효율적이었다. iterationCount=1로 기록.

### 7.2 Tools/Environment

- `idt-local-db-and-run-repro` 메모리에 로컬 DB 조회·JWT 토큰·TestClient 재현 레시피를 남겼다.
- dev 서버 중복 프로세스 정리 필요.

---

## 8. Next Steps

### 8.1 Immediate

1. dev 서버(포트 8000) 재시작 후 채팅 UI에서 동일 질문 재확인.
2. 커밋 시 작업 트리의 무관한 변경(fix-worker-id-name-length)과 분리.
3. `/pdca archive wiki-guided-routing`.

### 8.2 Next PDCA Cycle

- 표 추출 정확도(브라우저 "검색" 클릭 → 표 추출 → 페이지네이션) — MCP 서버 측 + 위키 지침 템플릿.
- (선택) `/wiki update`로 "위키 지침 우선 라우팅" 패턴을 위키에 기록 — 사용자 명시 호출 시에만.

---

## 9. Changelog

### v1.0.0 (2026-09-12)

- 목차 발췌(`wiki_toc_excerpt_chars`, SQL SUBSTRING) 및 위키 지침 프레이밍
- 수퍼바이저 `[위키 지침 처리 기준]` 조건부 블록, `[직전 수집 실패]` 블록 + `last_worker_error` 상태
- `ToolErrorPolicy`(도메인), collect 노드 실패 신호
- 도구 편집 시 `## Tool Guidelines` 섹션 한정 재생성
- 테스트 12파일(신규 2)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-12 | 완료 보고서 | 배상규 |
