# judgment-backend Completion Report

> **Status**: Complete (실호출 검증은 환경 미확보로 이월)
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-10-16
> **PDCA Cycle**: Plan → Design → Do(4 module) → Check(96%) → Act-1(99%) → Report

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | judgment-backend — Jev(TypeSafe)·AnyJev(폐쇄망) 타입 판정 포트 + `search_decision` 결선 |
| Start Date | 2026-10-15 |
| End Date | 2026-10-16 |
| Duration | 2일 (세션 1: Plan+Design, 세션 2: Do m1-2, 세션 3: Do m3-4 + Check + Act) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 98%                        │
├─────────────────────────────────────────────┤
│  ✅ Complete:     FR 15/15, DoD 9/10          │
│  ⏳ Carried over:  실호출 스모크(L3) + 테스트 보강 5건 │
│  ❌ Cancelled:     0                          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 판정형 LLM 호출이 전부 생성 모델 `with_structured_output`에 묶여 있어 판정 전용 모델(Jev)로 바꿀 수 없었고, 폐쇄망 대체(AnyJev)를 끼울 포트가 없었다. |
| **Solution** | `domain/judgment` 포트(Noul/Choice → 확률) + Jev(`typesafe-sdk`)·AnyJev(HTTP) 어댑터 + `JUDGMENT_BACKEND=jev\|anyjev\|off` 팩토리. 첫 소비 지점 `search_decision`을 Noul 1개 + 임계값으로 교체하고, 백엔드 실패·미설정은 기존 LLM 어댑터로 폴백. |
| **Function/UX Effect** | 화면·API 변화 0. 기본값 `off`라 배포 동작 불변(전체 회귀 FAILED 목록 master와 diff 0, 10,669 passed). `.env` 한 줄로 백엔드 전환. 실패 경로 11종(타임아웃·4xx/5xx·연결·디코딩·스키마·타입 혼합·임계값 오설정)이 전부 폴백으로 흡수됨을 테스트로 고정. |
| **Core Value** | 판정 백엔드가 설정으로 교체되는 코어 일반 모듈. 벤더 특성(SDK vs HTTP, Noul 라벨, confidence 유무)은 어댑터 안에 격리돼 다음 소비 지점은 질문만 얹으면 된다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~15 구현·테스트 통과 | ✅ Met | 관련 테스트 128 passed; Check FR 15/15 (Act-1 후) |
| SC-2 | 전송 픽스처 5케이스 × 2백엔드 × Noul/Choice | ⚠️ Partial | 5케이스 × 2백엔드 완비, Choice 실패 케이스는 라벨 불일치·타입 혼합만 (G8 이월) |
| SC-3 | 팩토리 4실패→None·2정상 | ✅ Met | `test_factory.py` 10건, `test_judgment_di.py` None+warning 1회 |
| SC-4 | search_decision 임계값 경계·폴백 | ✅ Met | 0.49/0.50/0.51, 실패 3종 + 외부 wait_for → fallback 1회 |
| SC-5 | `off`에서 기존 테스트 무수정 통과 | ✅ Met | 전체 스위트 3회 실행 모두 FAILED 53건 = master 기준, test id diff 0 |
| SC-6 | AST 경계 + `_DECLARED_CONSUMERS` | ✅ Met | `test_module_boundaries.py` 5건, 외부 참조 2파일만 |
| SC-7 | `-m llm` 스모크 2종 작성, 실행 이월 | ✅ Met | `test_real_backend_smoke.py` — env 없을 때 2 skipped |
| SC-8 | 회귀 FAILED diff 0 | ✅ Met | 위 SC-5 |
| SC-9 | Design 확정(AnyJev 스키마·SDK 버전·질문) | ✅ Met | Design D1~D3·D8, §4.5 |
| QC | 커버리지 ≥90%, domain 100% | ✅ Met | Act-1 후 신규 모듈 98%, `value_objects.py` 100% |

**Success Rate**: 9/10 Met, 1 Partial (90%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 범위 = 모듈 + 소비 지점 1곳(`search_decision`) | ✅ | 결선까지 끝나 "미배선 모듈" 전례(intent-analyzer) 회피 |
| [Plan] | AnyJev는 별도 HTTP 서비스만 | ✅ | torch 의존 0, 어댑터는 httpx 하나 |
| [Plan] | 실패 시 기존 LLM 어댑터 폴백 | ✅ | "없던 상태"=기존 동작. 11종 실패 경로 테스트 |
| [Plan] | `typesafe-sdk` 사용 | ✅ | 0.7.5, `httpx2` 의존이라 충돌 없음 |
| [Plan] | 실호출 불가 → 픽스처 계약 + 이월 | ✅ | 문서 예시 응답 그대로 픽스처. 위키 "fake만으로 완료 금지"의 명시적 예외 |
| [Design] | D1 AnyJev Noul 네이티브(Plan 정정) | ✅ | 소스(`tacit.py`·`readout.py`) 확인. 에뮬레이션 코드 0 |
| [Design] | D9 SDK 재시도 0 / D8 압축 off | ✅ | 지연 상한 유지. D8 근거는 Check G6에서 정정 |
| [Design] | D10 예외 3종 정규화, 흡수는 소비 지점 1곳 | ✅ (Act-1 보강) | AnyJev `RequestError`·`TypeError` 누락을 G1로 적발·수정 |
| [Design] | D11 domain은 dataclass(pydantic 금지) | ✅ | AST 테스트로 강제 |
| [Design] | D15 lifespan `aclose()` best-effort | ✅ | `_close_judgment_backend()` |
| [Design] | D17 질문 상수는 소비 지점 소유 | ✅ | `search_decision/questions.py` 1곳 |
| [Design→Act] | §4.3 임계값 ValueError(fail-fast) | 🔄 변경 | Check G5: prompt_guard 선례와 맞춰 조립 실패 흡수(warning + 기존 어댑터)로 바꿈 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [judgment-backend.plan.md](../01-plan/features/judgment-backend.plan.md) | ✅ (FR-06 D1 정정 반영) |
| Design | [judgment-backend.design.md](../02-design/features/judgment-backend.design.md) | ✅ v0.2 (D3·D6·D8·§6.1·§11.1 갱신) |
| Check | [judgment-backend.analysis.md](../03-analysis/judgment-backend.analysis.md) | ✅ v0.2 (Act-1 반영) |
| Report | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | domain stdlib만 | ✅ | AST 테스트 |
| FR-02 | 다중 질문·qid 매핑 | ✅ | |
| FR-03 | 확률 검증 → ProtocolError | ✅ | |
| FR-04 | Jev 명시 인자·`http_client` 주입 | ✅ | base_url None 시 SDK env 폴백은 경계 사례(G7 이월) |
| FR-05 | 응답 model 보존 | ✅ | |
| FR-06 | AnyJev `/v1/decide` Noul/Choice | ✅ | D1 정정대로 네이티브 noul |
| FR-07 | probs 검증·extra 보존 | ✅ | `reasoning_tokens` 포함(Act-1) |
| FR-08 | 타임아웃·예외 정규화 | ✅ | Act-1에서 `RequestError`·`TypeError` 보강 |
| FR-09 | 팩토리 None·1회 조립 | ✅ | |
| FR-10 | `p >= threshold` | ✅ | |
| FR-11 | 폴백 | ✅ | |
| FR-12 | main.py 조립·시그니처 불변 | ✅ | `_build_search_decision()` 헬퍼로 분리(Act-1) |
| FR-13 | 질문은 소비 지점 소유 | ✅ | |
| FR-14 | 로그 원문 금지 | ✅ | 길이·SHA-256 앞 12자만 |
| FR-15 | `.env.example` | ✅ | 이번엔 Bash append로 기록 성공 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 호환성 | `off`에서 회귀 0 | FAILED diff 0 (3회) | ✅ |
| 가용성 | 백엔드 장애 시 흐름 중단 0 | 실패 11종 폴백 테스트 | ✅ |
| 의존성 | SDK optional, 미설치 기동 | `ImportError`→None 테스트 | ✅ |
| 아키텍처 | 외부 참조 2파일 | AST 테스트 | ✅ |
| 보안 | 키·state 로그/예외 미노출 | 테스트 2건 | ✅ |
| 커버리지 | ≥90% / domain 100% | 98% / 100% | ✅ |
| 지연 | 실측 | — | ⏳ 이월(실호출) |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 포트·VO·예외 | `src/domain/judgment/` (4) | ✅ |
| Jev·AnyJev 어댑터·팩토리 | `src/infrastructure/judgment/` (8) | ✅ |
| 소비 지점 어댑터·질문 | `src/infrastructure/search_decision/{judgment_adapter,questions}.py` | ✅ |
| 조립 | `src/api/main.py` (+70/−1: `get_judgment_backend`, `_build_search_decision`, `_close_judgment_backend`, lifespan) | ✅ |
| 설정 | `src/config.py` 8키, `.env.example`, `pyproject.toml` extra `judgment` | ✅ |
| 테스트 | 8파일 + 픽스처 4 (총 128건, llm 2 skip) | ✅ |
| 문서 | Plan·Design v0.2·Analysis v0.2·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 실호출 스모크(L3) + 양성 대조군 벤치 → 임계값 조정 | Jev 키·AnyJev 서버 미확보(Plan 결정) | High | 환경 확보 후 0.5일 |
| G8 실패 케이스 Choice parametrize | 시간 | Low | 0.5h |
| G4 폴백 자체 예외 시뮬레이션 | 기존 어댑터 catch-all에 의존 | Low | 0.5h |
| G10 스모크 `/health` 선조건 | 실호출과 함께 | Low | 0.2h |
| G11 `aclose` 실패 warning 테스트·singleton 테스트 클라이언트 정리 | 시간 | Low | 0.5h |
| G7 `typesafe_base_url=None` 시 SDK 기본 URL 명시 전달 | 경계 사례 | Low | 0.2h |
| 운영 활성화(`JUDGMENT_BACKEND` on) | 실호출 검증 전엔 off 유지 | — | 벤치 후 결정 |

### 4.2 Cancelled/On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| Noul yes/no 에뮬레이션 | AnyJev가 noul 네이티브 지원 | `kind:"noul"` |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Check | Act-1 후 |
|--------|--------|-------|----------|
| Design Match (static) | 90% | 96.0% | **99.3%** |
| 런타임 포함 | — | 97.4% | 99.5% |
| Critical / Important | 0 / 0 | 0 / 1 | **0 / 0** |
| 신규 모듈 커버리지 | 90% | 96% | 98% (domain 100%) |
| 전체 회귀 | diff 0 | diff 0 | diff 0 (10,669 passed) |
| ruff(E,F,I,N,W,UP) | 0 | 0 | 0 |

### 5.2 Resolved Issues (Act-1)

| Issue | Resolution | Result |
|-------|------------|--------|
| G1 AnyJev `DecodingError`·`TypeError` 미정규화 → 엑셀 분석 중단 가능 | `except httpx.RequestError`, `(ValueError, TypeError)` | ✅ 테스트 3건 |
| G5 임계값 오설정 시 앱 기동 실패 | `_build_search_decision()`에서 흡수 → warning + 기존 어댑터 | ✅ 테스트 3건 |
| G12 domain 커버리지 95% | 방어 분기 테스트 6건 | ✅ 100% |
| G2·G6·G9·Plan FR-06 문서 불일치 | Design/Plan 갱신 | ✅ |

---

## 6. Lessons Learned

### 6.1 Keep

- **외부 계약은 Design 단계에서 소스로 확인한다.** README만 믿었던 Plan 가정 2개(AnyJev Noul 미지원, SDK httpx 충돌)가 `tacit.py`·`readout.py`·PyPI 메타데이터 확인으로 뒤집혔다. 구현 전에 잡혀 코드 낭비 0.
- **전송 계층 주입(`httpx.MockTransport` / `httpx2.MockTransport`)** 으로 SDK·HTTP 양쪽을 실호출 없이 계약 테스트할 수 있었다. 두 어댑터 모두 첫 실행에서 통과.
- **포트는 던지고 흡수는 한 곳**(degradation 경계 위키) — Check에서 "삼키는 곳이 한 곳"이라 G1 수정이 2줄로 끝났다.
- **조립 헬퍼 분리**(`_build_search_decision`)가 G3(런타임 단언 불가)과 G5(기동 실패)를 한 번에 풀었다.

### 6.2 Problem

- **`ruff format`을 `main.py` 전체에 실행**해 6천 줄이 재포맷됐다(diff 630). `git checkout` 후 수기 재적용. 공용 대형 파일은 Edit로만 건드려야 한다.
- **백그라운드 전체 스위트 중에 `uv run`을 실행**해 uv가 editable 패키지를 재빌드, 허위 수집 ERROR 2건이 났다(단독 재실행 통과). 회귀 중엔 다른 `uv run` 금지.
- Design D8 근거("zstd 미설치 시 비압축")가 SDK docstring과 달랐다 — 구현이 맞고 문서가 틀린 사례. 문서의 "근거" 문장도 소스 확인 대상.
- 임계값 범위 오류를 Design은 fail-fast로 적었지만 프로젝트 선례(prompt_guard mode 오타 → 조립 실패 흡수)와 어긋났다. 신규 config 검증 정책은 선례부터 확인.

### 6.3 Try

- 실호출 환경이 생기면 **양성 대조군 벤치**(웹검색 필요 N건 + 불필요 M건)로 임계값·백엔드별 캘리브레이션 차이를 측정한 뒤 `on`으로 전환.
- 두 번째 소비 지점(RAG 관련성 `relevance_adapter` 또는 인젝션 판정)을 같은 포트에 얹어 "질문만 얹으면 된다"를 실증.
- 대형 파일 포맷은 `ruff format --diff`로 먼저 범위 확인.

---

## 7. Process Improvement Suggestions

| Phase | Current | Suggestion |
|-------|---------|------------|
| Plan | 외부 라이브러리 가정을 README 기준으로 작성 | Plan에 "소스 확인 필요" 표시를 두고 Design에서 전수 확인 |
| Do | 회귀 실행과 다른 명령이 겹칠 수 있음 | 전체 스위트는 세션 끝에 1회, 그동안 `uv run` 금지 |
| Check | gap-detector가 테스트 실행 불가 | 오케스트레이터가 런타임 결과(테스트·회귀·커버리지)를 먼저 모아 넘김(이번 방식 유지) |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋: `feature/judgment-backend` — `idt/src/{domain,infrastructure}/judgment`, `search_decision/{judgment_adapter,questions}.py`, `config.py`, `main.py`(+70/−1), `pyproject.toml`, `.env.example`, tests, docs
- [ ] `/pdca archive judgment-backend`
- [ ] 사용자 `/wiki update` 시 후보: "판정 포트 + 폴백 어댑터" 패턴, 실호출 이월 체크리스트 항목

### 8.2 Next PDCA Cycle

| Item | Priority | Trigger |
|------|----------|---------|
| judgment-live-verification (스모크·벤치·임계값) | High | Jev 키 또는 AnyJev 서버 확보 |
| 두 번째 소비 지점(relevance / prompt_guard judge) | Medium | 벤치 결과 양호 시 |
| Score 프리미티브(리랭크) | Low | 두 번째 소비 지점 이후 |

---

## 9. Changelog

### judgment-backend v1 (2026-10-16)

**Added:**
- `src/domain/judgment/` — `JudgmentPort`, Noul/Choice 질문·답 VO, `JudgmentError` 3종
- `src/infrastructure/judgment/` — `JevJudgmentAdapter`(typesafe-sdk 0.7.x), `AnyJevJudgmentAdapter`(`POST /v1/decide`), `build_judgment_backend()`
- `src/infrastructure/search_decision/judgment_adapter.py`, `questions.py` — Noul 판정 + LLM 폴백
- `config.py` 8키(`JUDGMENT_BACKEND=off` 기본), `.env.example` 블록, `pyproject` extra `judgment`
- `main.py` — `get_judgment_backend()`, `_build_search_decision()`, `_close_judgment_backend()`
- 테스트 128건(+ llm 스모크 2 skip), 픽스처 4

**Changed:**
- `main.py` `create_analyze_excel_use_case`의 `search_decision` 조립이 헬퍼 경유(백엔드 없으면 기존 객체 그대로)

**Fixed:**
- (Act-1) AnyJev 디코딩 오류·타입 혼합 응답이 폴백되지 않던 경로

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-16 | 완료 보고서 | 배상규 |
