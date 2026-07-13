# rag-routed-integration 완료 리포트

> **Feature**: rag-routed-integration (에이전트 RAG 도구 라우팅 검색 opt-in — 교차검증 구조)
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트 풀스택)
> **Author**: 배상규
> **Period**: 2026-07-09 (Plan → Report, 단일 세션 — Plan은 사용자 피드백으로 1회 개정)
> **Final Match Rate**: **99%** (최초 96% → Low 3건 즉시 해소)
> **Status**: ✅ Completed — **라우팅 검색이 실제 제품 경로(에이전트 대화)에 연결, 기존 검색 체계 완전 보존**

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | rag-routed-integration |
| 기간 | 2026-07-09 (Plan·개정·Design·Do·Check·Report) |
| PDCA 흐름 | Plan ✅(피드백 개정) → Design ✅ → Do ✅ → Check ✅ (99%) → Report ✅ |
| 아키텍처 | Thin DDD, 풀스택 |
| 맥락 | 검색 파이프라인 4부작(청킹→섹션→문서 요약→라우팅 API)의 **첫 실사용 연결** |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 99% (D1~D11 반영, FR-03 기준선·FR-07 누수 0 코드 검증) |
| 변경 규모 | 백엔드 수정 5 + 프론트 수정 3 (신규 프로덕션 파일 0 — 분기·필드만) |
| **마이그레이션 / config / search_mode 체계 변경** | **0 / 0 / 0** |
| 신규 테스트 | 백엔드 17(도구 분기 11 + 팩토리 3 + VO 3, test_tools_routed.py 220 LOC) + 프론트 3 |
| 회귀 | 0 (agent_builder·rag_agent 686건 그린, **기존 도구 테스트 무수정 통과 = 기준선 증명**, 프론트 tsc 0) |

### 1.3 Value Delivered

| Perspective | 전달된 가치 (실측) |
|-------------|---------------------|
| **Problem** | 라우팅 검색이 검증 API로만 존재해 에이전트가 쓰지 못했고, 최초 설계(search_mode 값 추가)는 기존 검색 방식을 대체(갈아끼우기)해 교차검증이 불가능했음 — 사용자 피드백으로 방향 전환. |
| **Solution** | `RagToolConfig.use_routed_search: bool = False` 독립 opt-in — 에이전트 생성 시 선택 → tool_config JSON으로 DB 저장 → 도구가 분기. 켜면 3계층 라우팅, **끄거나 강등되면 그 에이전트의 기존 search_mode 경로 그대로**(강등 4사유 reason 코드 관측). 결과는 `[출처: 문서명 > 조 제목]` + 요약 1줄 + 본문으로 LLM 전달. |
| **Function/UX Effect** | 빌더 RAG 설정에 토글 하나("라우팅 검색 (3계층 요약)") — 기존 검색 모드 라디오와 병존. 같은 구성의 에이전트를 토글만 달리해 **나란히 교차검증** 가능. LLM 답변의 근거 인용 품질 향상. |
| **Core Value** | 4부작의 실사용 관측 시작 — record_retrieval metadata(`search=routed`)·강등률 로그가 라우팅 품질과 백필 우선순위, 기본값 전환 판단의 데이터가 됨. 권한 게이트·visibility 필터는 강등 구조로 누수 방향 원천 차단. |

---

## 2. 구현 범위

### 2.1 백엔드 (수정 5)

| 파일 | 변경 |
|------|------|
| `domain/agent_builder/rag_tool_config.py` | `use_routed_search: bool = False` (use_wiki_first 동형, D1) |
| `application/agent_builder/schemas.py` | `RagToolConfigRequest` 동기 — `model_dump()` 경유 DB 자동 저장 |
| `application/rag_agent/tools.py` | 분기 5메서드 — `_routed_search`(강등 4사유)·`_routed_scope`(필터 3분류)·`_routed_degrade`·`_format_routed_results`(근거 헤더+요약 150자)·`_record_routed_retrieval`(metadata routed 표기) |
| `infrastructure/agent_builder/tool_factory.py` | `routed_retrieval_getter` additive + 도구 필드 전달 |
| `api/main.py` | 에이전트 빌더 ToolFactory에 getter 연결(미들웨어 팩토리는 RAG 비실사용 컨텍스트로 의도적 제외 — not_wired 안전 강등) |

### 2.2 프론트 (수정 3)

- `types/ragToolConfig.ts` — 타입 + `DEFAULT_RAG_CONFIG`(false)
- `RagConfigPanel.tsx` — 토글 블록(자동 전환·교차검증 안내), 기존 라디오 무변경
- `RagConfigPanel.test.tsx` — 토글 on/off·라디오 불변 3케이스

---

## 3. 핵심 설계 결정 이행 (D1~D11: 11/11)

- **D3 강등의 목적지 = 그 에이전트의 기존 설정**: 범용 폴백이 아니라 search_mode 경로 복귀 — off 기준선과 강등 동작이 일치해 교차검증이 성립하는 구조적 핵심.
- **D4 필터 3분류**: `_apply_auth_filter`가 항상 키를 주입한다는 코드 확인(설계 단계)이 "부재 키 전부 강등 → 상시 강등" 함정을 사전 차단 — `kb_id` 매핑 / `viewer_department_ids` 무시(기존 hybrid와 동일 취급) / `visibility`·custom 강등.
- **D5 강등 4사유 관측**: `not_wired`/`filter_incompatible`/`error`/`empty` reason 코드 — 토글 실효성(강등률)을 로그로 판단.
- **D7 multi-query 우회**: routed 성공 시 원 질의만, 강등 시 원래 규칙 완전 재현.
- **D11 기준선 증명 전략**: "기존 테스트 무수정 통과"를 FR-03의 수용 기준으로 삼음 — 실제로 686건 무수정 그린.

## 4. Gap 처리 (Check 96% → 99%, 전부 Low)

| # | Gap | 조치 |
|---|-----|------|
| G1 | D2 "생성처 전수" 문구 vs 미들웨어 팩토리 미연결 | 설계 문서 정정(의도적 제외 사유 명시 — 코드가 정당) |
| G2 | error 강등 로그 스택 트레이스 손실 | `exception=e`로 수정(NFR-06) |
| G3 | VO 단위 테스트 공백 | 기본값·부재 키 복원·직렬화 왕복 3케이스 추가 |

## 5. 검증 결과

- **백엔드**: 신규 17건 포함 107건 + agent_builder·rag_agent 전체 686건 그린. gap-detector가 FR-01 저장 경로(`model_dump()` 자동 전파)·FR-07 누수 차단(visibility 강등 시 기존 경로에 권한 필터 유지)을 코드로 확인.
- **프론트**: RagConfigPanel 9건(신규 3) 통과, tsc 0 에러, 사전 실패 8건 외 신규 실패 0.
- **verify 핵심 검사**: print 0, exception= 전건, domain→infra 0. `import src.api.main` OK.

## 6. 후속 과제

1. **교차검증 실측 (즉시 가능)**: 동일 구성 + 토글 on/off 에이전트 쌍 생성 → 동일 질문 비교. 강등률은 reason 로그, 검색 품질은 record_retrieval metadata로 관측.
2. **agent-tool-config-update**: 에이전트 수정 시 tool_config 갱신 — 기존 에이전트의 토글 전환 허용(현재는 생성 시만).
3. **routing-quality-eval**: 교차검증 데이터 + RAGAS 비교 → K/N/weights 튜닝·기본값 전환 판단.
4. **section-summary-backfill**: 강등·폴백률 높은 KB부터 일괄 요약.

## 7. 학습 노트

- **사용자 피드백이 설계의 축을 바꿨다**: "최소 변경(enum 값 추가)"이 항상 정답이 아니다 — 도입 철학이 교차검증이라면 직교 스위치가 맞다. 기존 필드의 의미 확장은 상호배타를 만들어 비교 기준선을 없앤다(메모리 저장: prefer-independent-optin-over-field-extension).
- **"강등의 목적지" 설계**: 폴백을 범용 기본값이 아니라 "해당 엔티티의 기존 설정"으로 정의하면, opt-in 기능의 off/실패 동작이 기준선과 일치해 A/B 비교가 공짜로 성립한다.
- **권한 필터의 상시 주입을 설계 전에 확인한 가치**: 코드 리딩 없이 "부재 키 강등" 규칙을 그대로 구현했다면 부서 권한 사용자 전원이 상시 강등되는 무의미한 토글이 됐을 것 — Plan/Design 단계 file:line 검증 관례의 배당.
