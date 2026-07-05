# Gap Analysis: compose-tool-instructions

> Design: `docs/02-design/features/compose-tool-instructions.design.md`
> 분석일: 2026-07-05 | 도구: gap-detector Agent
> **Match Rate: 100% (23/23)** — 최초 분석 95.7%(22/23), 누락 1건 당일 보완 완료

---

## 1. 결과 요약

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| 설계 결정 (D1~D5) | 5/5 | ✅ |
| 백엔드 상세 (§4) | 4/4 | ✅ |
| 프론트엔드 상세 (§5) | 4/4 | ✅ |
| 테스트 계획 (§7) | 10/10 | ✅ (보완 후) |
| **전체** | **23/23 (100%)** | ✅ |

## 2. 항목별 검증 근거 (요약)

### 설계 결정
| ID | 상태 | 근거 |
|----|:----:|------|
| D1 WorkerInfo.instruction 공용 확장 | Match | `application/agent_builder/schemas.py:47-48` |
| D2 프론트 변환 유틸 | Match | `utils/draftToolMapping.ts` |
| D3 mcp_{srv} → 서버 도구 전체 전개 | Match | `draftToolMapping.ts:15-21` |
| D4 지침 저장은 system_prompt 병합 | Match | 별도 저장 스키마 없음, 필드 주석 명시 |
| D5 `_normalize_tool_id` mcp: 처리 | Match | `create_agent_use_case.py:324-333` + dedup(`268-274`) |

### 백엔드/프론트 상세
- composer `_WorkerOutput.instruction` + `[도구 지침]` 프롬프트 규칙: `composer.py:34-40, 70-77` ✅
- use case 전파/`"; "` 병합/응답 노출: `compose_agent_use_case.py:203, 251-257, 307` ✅
- `handleApplyDraft` 변환 적용 + RAG 부수효과: `AgentBuilderPage/index.tsx:291, 295-301` ✅
- 카드 도구별 지침 접기 표시/빈 값 생략: `ComposeDraftCard.tsx:40-41, 92-117` ✅
- update use case: tool_ids 정규화 경로 자체가 없어 수정 불필요 (설계의 조건부 항목 — N/A 확인 완료)

## 3. 발견된 Gap과 조치

| # | 심각도 | 내용 | 조치 | 상태 |
|---|--------|------|------|:----:|
| 1 | Missing | RAG 부수효과 회귀 테스트 부재 — `handleApplyDraft`에서 RAG 도구 포함 시 `toolConfigs` 세팅 검증 테스트 없음 (프로덕션 코드는 구현됨) | `AgentBuilderStudio.test.tsx`에 "RAG 도구 포함 초안 적용 시 tool_configs가 세팅되어 저장에 포함된다" 추가, 통과 확인 | ✅ 해결 |
| 2 | 경미(Changed) | 유틸의 MCP 필터가 설계 pseudocode(`tool_id` startsWith 파싱)와 다르게 `mcp_server_id` 직접 비교로 구현 — 동작 등가이며 더 견고 | 코드를 truth로 두고 Design §5-1 pseudocode 갱신 | ✅ 해결 |
| 3 | 경미(문서) | Design §7의 D5 테스트 파일명 오기 (`test_create_agent_use_case.py` → `_mcp.py`) | Design 문서 정정 | ✅ 해결 |

## 4. 설계에 없는 추가 구현 (긍정적)

- `test_normalize_tool_id_formats` — 4가지 ID 형식 정규화 순수 단위 테스트
- 프론트 매핑 유틸 테스트 5케이스 (설계 요구 3케이스 + 혼합/중복제거 + 카탈로그 미로딩)
- MSW compose 목에 instruction 샘플 포함 — 통합 경로 검증 강화

## 5. 최종 테스트 현황

| 스위트 | 결과 |
|--------|------|
| 백엔드 composer + builder (`tests/application/agent_composer`, `agent_builder`, api 라우터) | 447 passed |
| 프론트 유틸/카드/Fix패널/스튜디오 통합 (RAG 회귀 포함) | 17+22 passed |
| 프론트 `tsc --noEmit` | 통과 |

## 6. 결론

Match Rate 100% — `/pdca report compose-tool-instructions` 진행 가능.
