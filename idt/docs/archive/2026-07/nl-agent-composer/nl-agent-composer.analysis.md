# Analysis: nl-agent-composer

> Created: 2026-07-04
> Phase: Check (Gap Analysis)
> Design: `docs/02-design/features/nl-agent-composer.design.md`
> Analyzer: gap-detector agent + 수동 확인
> **Match Rate: ≈ 95%** (엄격 38/41 = 92.7%, 부분일치 0.5 가중 39/41 = 95.1%) — **90% 기준 충족**

---

## 1. 검증 항목 총괄

| 카테고리 | 항목 수 | 일치 | 부분일치 | 불일치 |
|----------|:---:|:---:|:---:|:---:|
| 설계 결정 D1~D7 | 7 | 6 | 1 (D3) | 0 |
| 신규 파일 §2 (클래스/메서드/스키마 필드) | 11 | 11 | 0 | 0 |
| 기존 파일 변경 §3 | 4 | 4 | 0 | 0 |
| 테스트 설계 §4 (파일별) | 6 | 5 | 1 (router) | 0 |
| 요구사항 FR-01~FR-10 | 10 | 10 | 0 | 0 |
| 코딩 규칙 (신규 파일) | 3 | 2 | 0 | 1 → **수정 완료** |
| **합계** | **41** | **38** | **2** | **1 → 0** |

핵심 확인 근거:
- **D1** 프리필: `CreateAgentRequest.system_prompt` + Step 3 분기 (`create_agent_use_case.py`)
- **D2** 폴백: `_fallback_server_candidates` + `_FALLBACK_NOTE` + warning 로그
- **D4/D5** 신규 라우터 `POST /api/v1/agents/compose`, 빌더 LLM 패턴 DI (`main.py create_agent_composer_factories`)
- **D6** 내부=`get_all_tools()`, MCP=tool_catalog `source=="mcp"`
- **D7** clamp+notes, `derive_coverage` 서버 재산정
- **§2-5 조립 순서** drop→매핑/병합→clamp→재부여→프롬프트 절단→missing→coverage 정확 일치
- **FR-08** `_build_skeleton_from_tool_ids` async 전환 + `_resolve_mcp_description` (미등록/비활성 ValueError)
- **FR-10** start/done/failed + request_id + `exception=e` 로깅

## 2. Gap 목록 및 조치 결과

| # | 심각도 | 내용 | 조치 |
|---|--------|------|------|
| 1 | Med | `_assemble_draft` 76줄 — 함수 40줄 규칙 위반 | ✅ **수정 완료** — `_sanitize_workers` 헬퍼 추출(각 메서드 40줄 이내), 테스트 38건 재통과 |
| 2 | Low | D3의 `_parse_output` 확장점 미구현 (structured output이 파싱 객체를 직접 반환해 불필요) | 수용 — 기능 무해, 향후 2-call 전환 시 분리 |
| 3 | Low | 라우터 테스트 "인증 없음 401" 케이스 누락 (대신 coverage=none 케이스 추가) | 수용 — 실 auth 의존성은 DB 세션 체인이 필요해 단위 테스트 부적합(기존 tests/api 사전 실패 사례와 동일 맥락). E2E에서 확인 |
| 4 | Low | MCP 병합 시 sort_order가 최솟값이 아닌 최초 등장값 | ✅ **수정 완료** — `min(existing.sort_order, w.sort_order)` 적용 |
| 5 | Low | 헬퍼 명칭 `_resolve_mcp_meta`(설계) vs `_resolve_mcp_description`(구현) | 수용 — 기능 동등(cosmetic), 구현 명칭이 반환 타입을 더 정확히 표현 |

## 3. Design에 없는 구현 추가분 (충돌 없음)

| 추가분 | 성격 |
|--------|------|
| `_ComposeOutput.notes` (LLM 조합 근거 필드) | 응답 notes 품질 향상 |
| flow_hint 재계산 (워커가 보정된 경우 `" → ".join(tool_ids)`) | 초안-워커 정합성 보장 |
| 추가 테스트 6건 (name echo, clamp, inactive/no-repo/mixed MCP, mcp 프롬프트 생성) | 설계 최소셋 초과 커버 |

## 4. 테스트/검증 현황

- 신규 테스트 38건 통과 (Gap 1·4 수정 후 재확인)
- 회귀: `tests/application/agent_builder` 390 passed, `tests/domain` 1,923 passed
- `/verify-architecture` · `/verify-logging` · `/verify-tdd` 신규 파일 위반 0건

## 5. 결론

Match Rate ≈ 95% (즉시 조치 대상 Gap 1·4는 Check 단계 내 수정 완료). **iterate 불필요, Report 진행 가능.**

미검증 잔여(수동 확인 필요): Plan §6-3 E2E — 실 LLM/DB 환경에서 compose 초안 → `POST /agents` 저장 → run 실행 1회.
