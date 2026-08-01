# Builtin Tools Gap Analysis

> **Design**: `docs/02-design/features/builtin-tools.design.md`
> **Analyzer**: gap-detector (Design D1~D9·§5.2 알고리즘·§6 T1~T6·§7 프론트 설계 전수 대조)
> **Date**: 2026-08-01
> **Match Rate**: 최초 93% (Match 69 · Partial 5 · Missing 0 / 74항목) → **보강 후 100%** (§4)
> **판정**: 품질 기준(≥90%) 충족 → Report 진행 가능

---

## 1. 요약

Design의 백엔드 결정(D1~D7)은 파일·라인 수준까지 전부 일치(Missing 0). 무관 파일 오염 0건.
Partial 5건은 모두 테스트 커버리지 또는 사소한 표기/시점 차이이며 기능 결함은 발견되지 않았다.

## 2. Gap 목록

| # | 심각도 | Gap | 근거 |
|---|:--:|---|---|
| G1 | **Medium** | 설계 §7.3 ③ "Fix 초안 적용 → excludedBuiltinTools 불변 + form.tools 빌트인 미혼입" 테스트 부재 — 채팅 우회 차단의 프론트 절반(`handleApplyDraft` 필터)이 회귀 미보호 | 구현 `AgentBuilderPage/index.tsx:318-323` / 테스트 파일에 초안 케이스 0건 |
| G2 | Low | 관리자 화면 "활성" 컬럼 미구현 — 단 `GET /tool-catalog` 응답에 `is_active`가 없어 현 계약으론 구현 불가(설계 측 오류, 목록이 active만 반환하므로 실익도 없음) | `AdminToolsPage/index.tsx:71-76`, `schemas.py:5-13` |
| G3 | Low | §5.2 `seen.add` 시점 차이(설계: skip 직후 / 구현: description 해석 성공 후) — 비활성 MCP 서버의 빌트인 도구 2개↑일 때 조회·경고 로그 중복(기능 영향 없음) | `create_agent_use_case.py:333-338` |
| G4 | Low | `CatalogTool.is_builtin`이 optional(`?`) — 설계는 required. 백엔드는 항상 반환하므로 타입이 실제보다 느슨 | `toolCatalog.ts:10` |
| G5 | Low | T2 ②③(재sync 왕복 보존) sync UseCase 레벨 부재 — repo 레벨 계약 테스트로 대체됨 | `test_sync_internal_tools_use_case.py:93-119` |

**역방향(구현 초과, 전부 무해)**: edit 모드 빌트인 일반 도구 격하 동작+테스트, `SetBuiltinRequest/Response` 프론트 타입, `_resolve_builtin_description` 헬퍼(40줄 규칙), 테스트 초과 5건(T5 2건·ToolPickerModal 2건·PATCH 404), `models.py nullable=False`.

## 3. 권고 조치

1. **(즉시, G1)** `AgentBuilderPage/index.test.tsx`에 초안 적용 케이스 추가 — 초안이 빌트인 카탈로그 ID를 포함해도 ⓐ form.tools 미혼입 ⓑ excludedBuiltinTools 불변 단언
2. **(문서 갱신 — 코드가 진실)** §7.2 "활성" 컬럼 삭제(G2), §5.2 seen.add 시점 표기 정정(G3), §7.1 edit 모드 격하 동작·pendingToolId 가드 명시
3. **(선택)** `is_builtin` required 강화(G4), sync UseCase 레벨 왕복 보존 테스트(G5)

## 4. 보강 조치 결과 (2026-08-01, Act)

| # | 조치 | 검증 |
|---|------|------|
| G1 | `AgentBuilderPage/index.test.tsx`에 "Fix 초안 적용 → form.tools 빌트인 미혼입 + excluded 불변 + 저장 payload 검증" 케이스 추가 | vitest 통과 (Fix 탭 → compose → 적용하기 → 저장 전 구간 실동작 검증) |
| G2 | 설계 §7.2 "활성" 컬럼 삭제 + 사유 명기 (설계 측 오류 — 코드가 진실) | Design v0.2 |
| G3 | 설계 §5.2 `seen.add` 시점을 구현(해석 성공 후)에 맞춰 정정 | Design v0.2 |
| G4 | `CatalogTool.is_builtin` required 강화 + 픽스처 5파일 정비 | tsc 잔여 에러 0, 영향 테스트 51+19건 통과 |
| G5 | sync UseCase 레벨 재부팅 왕복 보존 테스트 추가 (보존 성질 모사 fake repo) | pytest 10/10 통과 |
| §7.1/§7.2 | edit 모드 격하 동작·pendingToolId 가드 설계 명시 | Design v0.2 |

**보강 후 Match Rate: 100%** (Partial 5건 전부 해소 — G1/G4/G5 코드 보강, G2/G3 설계 정정)

## 5. 이월 확인

- Plan §8.2 수동 E2E 3종 미수행 (서버 기동 필요)
- **배포 시 V054 적용 필수** — 미적용 시 tool_catalog 조회 SQL 에러
- Plan/Design 문서 Status `Draft` — 승인 처리 필요
