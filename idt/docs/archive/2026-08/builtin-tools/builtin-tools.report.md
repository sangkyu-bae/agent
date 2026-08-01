# Builtin Tools Completion Report

> **Feature**: builtin-tools — 빌트인 도구(생성 시 자동 주입) + 관리자 등록/해제
> **Date**: 2026-08-01 (Plan → Report 동일일 완료)
> **Match Rate**: 최초 93% → 보강 후 **100%** (74항목, Missing 0)
> **Documents**: [Plan](../01-plan/features/builtin-tools.plan.md) · [Design](../02-design/features/builtin-tools.design.md) · [Analysis](../03-analysis/builtin-tools.analysis.md)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | builtin-tools |
| 기간 | 2026-08-01 (Plan~Report 1일) |
| Match Rate | 93% → 보강 후 100% (Act 1회) |
| 변경 규모 | 백엔드 신규 2 + 수정 12 파일, 프론트 신규 2 + 수정 12 파일, 마이그레이션 V054 |
| 테스트 | 백엔드 신규 17케이스(51건 통과) · 프론트 신규/보강 3파일(70건+ 통과), 회귀 백 506·프론트 111+19 무회귀 |

### 1.3 Value Delivered

| Perspective | Delivered |
|-------------|-----------|
| **Problem** | wiki_read/wiki_list 같은 표준 도구도 사용자가 직접 골라야만 붙었고, 빠뜨리면 위키를 쌓아도 에이전트가 열람 불가. 기본 도구 집합 변경은 코드 배포 필요 |
| **Solution** | `tool_catalog.is_builtin`(V054, 관리자 토글 SoT) + `ToolMeta.builtin_default`(프레시 DB 시드) 이원화. `CreateAgentUseCase` Step 2.7에서 모든 생성 경로에 자동 주입(중복 방지·MCP 장애 격하·상한 제외). `exclude_builtin_tool_ids` 명시 필드로만 제외 — 채팅(Fix) 경로엔 이 필드가 없어 LLM 우회가 구조적으로 불가 |
| **Function/UX Effect** | 신규 에이전트는 만들자마자 위키 열람/탐색 탑재. 생성 폼에 "기본" 배지+기본 선택, 수동 해제만 가능. 관리자는 `/admin/tools`에서 배포 없이 빌트인 지정/해제 (internal+MCP 모두) |
| **Core Value** | "플랫폼 표준 도구"를 데이터(카탈로그 플래그)로 선언하는 확장점 — 일반화>특화 원칙 부합. 이후 새 표준 도구(메모리·검색 등)도 관리자 등록만으로 전 신규 에이전트에 보급 |

---

## 2. 구현 요약

### 2.1 백엔드 (idt)

| 영역 | 내용 | 핵심 파일 |
|------|------|-----------|
| 스키마 | `is_builtin` TINYINT(1) DEFAULT 0 + COMMENT, wiki 2종 UPDATE 시드 | `db/migration/V054__add_tool_catalog_is_builtin.sql` |
| 시드 이원화 (D1) | `ToolMeta.builtin_default` — sync INSERT 시에만 적용, 런타임 SoT는 DB | `tool_registry.py`, `sync_internal_tools_use_case.py` |
| 보존 계약 (D2) | upsert UPDATE 분기에 is_builtin 불포함 — SQL 컴파일 검사로 계약 테스트화 | `tool_catalog_repository.py` |
| 관리자 API (D3/D4) | `PATCH /api/v1/tool-catalog/builtin` (admin 403/404 처리), 목록 응답 `is_builtin` 노출 | `tool_catalog_router.py`, `set_builtin_use_case.py` |
| 자동 주입 (D5/D6) | Step 2.7 — 정규화 dedup·exclude·MCP 격하·sort_order 연속·flow_hint 미포함·상한 제외·optional repo 무회귀 | `create_agent_use_case.py` (`_build_builtin_workers`) |

### 2.2 프론트 (idt_front)

| 영역 | 내용 | 핵심 파일 |
|------|------|-----------|
| 계약 동기화 | `CatalogTool.is_builtin`(required), `exclude_builtin_tool_ids`, `TOOL_CATALOG_BUILTIN`, `setBuiltin`/`useSetToolBuiltin` | types/services/hooks/constants |
| 생성 폼 (D8) | `excludedBuiltinTools` 전용 상태 — ToolPickerModal("기본" 배지·전용 콜백)과 빌트인 칩에서만 토글. Fix 초안 적용은 불변 + 초안의 빌트인 혼입 필터 | `AgentBuilderPage/index.tsx`, `ToolPickerModal.tsx`, `LeftConfigPanel.tsx` |
| 관리자 화면 (D9) | `/admin/tools` — 카탈로그 테이블 + `role="switch"` 토글, 행 단위 pendingToolId 가드 | `AdminToolsPage/index.tsx`, `App.tsx`, `adminNav.ts` |

### 2.3 핵심 설계 포인트: 채팅 우회의 구조적 차단

opt-out은 백엔드 요청 필드(`exclude_builtin_tool_ids`)와 프론트 전용 상태(`excludedBuiltinTools`)의 2중 구조로만 가능하다. Fix 에이전트(compose)는 무저장 초안이고 이 필드/상태에 접근하는 코드 경로가 없으므로, LLM이 어떤 초안을 생성해도 빌트인은 유지된다 — 프롬프트 방어가 아닌 구조적 보장 (G1 테스트로 회귀 고정).

## 3. Check/Act 결과

- gap-detector 74항목 전수 대조: Match 69 · Partial 5 · **Missing 0** (93%)
- Act 보강 1회로 Partial 5건 전부 해소 → **100%**: G1(초안 적용 불변식 프론트 테스트), G4(is_builtin required), G5(재부팅 왕복 보존 UseCase 테스트), G2/G3(설계 문서 정정 — 코드가 진실)
- verify-architecture: 신규 위반 0건

## 4. 교훈 (Lessons Learned)

1. **opt-out 채널의 구조적 분리** — "LLM이 빼면 안 되고 사용자는 뺄 수 있어야 한다"는 요구는 프롬프트가 아니라 *요청 스키마/상태 접근 경로의 분리*로 푸는 것이 확실하다.
2. **upsert 보존은 암묵이 아닌 계약으로** — 기존 UPDATE 분기가 우연히 플래그를 보존하는 성질을 SQL SET 절 검사 테스트로 명시 계약화해 미래 회귀를 차단.
3. **시드 이원화** — 마이그레이션 UPDATE(기존 DB)와 코드 기본값(프레시 DB INSERT)을 병행해야 양쪽 모두 커버되고, 보존 계약 덕에 관리자 설정과 충돌하지 않는다.
4. vitest는 `--pool=threads`에도 다중 워커 기동 타임아웃 발생 — `--maxWorkers=1` 필요 (Windows).

## 5. 이월 항목

| 항목 | 내용 |
|------|------|
| **배포 필수** | V054 미적용 시 tool_catalog 조회 SQL 에러 (모델에 컬럼 존재) |
| 수동 E2E 3종 | ① 관리자 등록/해제 반영 ② 채팅 생성 시 위키 도구 포함(빼달라고 해도 유지) ③ 폼 해제 후 미포함 — 서버 기동 시 일괄 |
| 후속 후보 | 기존 에이전트 일괄 백필(스냅샷 결정으로 소급 없음), config 필요 도구(RAG류)의 빌트인화, `is_active` 카탈로그 응답 노출 |
| 커밋 | 미수행 — git-workflow로 브랜치/커밋/PR 진행 필요 |

---

| Version | Date | Author |
|---------|------|--------|
| 1.0 | 2026-08-01 | 배상규 |
