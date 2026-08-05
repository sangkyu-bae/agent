---
title: 빌트인 도구 — opt-out 채널 구조 분리 + upsert 보존 계약 (V054)
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/docs/archive/2026-08/builtin-tools/builtin-tools.report.md
  - idt/db/migration/V054__add_tool_catalog_is_builtin.sql
  - idt/src/application/agent_builder/create_agent_use_case.py (_build_builtin_workers, Step 2.7)
  - idt/src/infrastructure/tool_catalog/tool_catalog_repository.py (upsert UPDATE 분기)
confidence: 0.9
version: 1
created: 2026-08-03
updated: 2026-08-03
verified_at: 4f650d3c
---

## 문제

wiki_read/wiki_list 같은 표준 도구를 사용자가 직접 골라야만 붙었고, 빠뜨리면 에이전트가
위키를 열람하지 못했다. 동시에 "LLM(Fix 채팅)은 빼면 안 되고, 사용자는 뺄 수 있어야 한다"는
비대칭 요구가 있었다.

## 검증된 사실

1. **SoT 이원화**: 런타임 SoT는 `tool_catalog.is_builtin`(V054, 관리자 토글).
   `ToolMeta.builtin_default`는 프레시 DB의 sync INSERT 시드에만 쓰인다.
   마이그레이션 UPDATE(기존 DB) + 코드 기본값(신규 DB)을 병행해야 양쪽이 커버된다.
2. **upsert 보존 계약**: tool_catalog upsert의 UPDATE 분기는 `is_builtin`을 SET 절에
   포함하지 않는다 — sync 재실행이 관리자 설정을 덮지 않는 성질을 "우연"이 아니라
   **SQL SET 절 컴파일 검사 테스트**로 명시 계약화했다. upsert 수정 시 이 테스트가 지킴이.
3. **자동 주입**: `CreateAgentUseCase` Step 2.7이 모든 생성 경로에서 빌트인을 주입한다
   (정규화 dedup, MCP 장애 시 격하, 워커 상한 계산에서 제외, optional repo 무회귀).
4. **opt-out은 구조로 차단**: 제외는 요청 필드 `exclude_builtin_tool_ids`(+프론트 전용 상태
   `excludedBuiltinTools`)로만 가능하다. Fix/compose 채팅 경로에는 이 필드에 접근하는 코드
   경로 자체가 없어 **LLM이 어떤 초안을 내도 빌트인은 유지** — 프롬프트 방어가 아니라
   스키마/상태 접근 경로 분리에 의한 구조적 보장 (G1 테스트로 회귀 고정).
5. **소급 없음**: 기존 에이전트의 도구 구성은 생성 시점 스냅샷 — 빌트인 지정이 소급
   주입되지 않는다 (백필은 후속 후보).
6. **배포**: V054 미적용 시 tool_catalog 조회 자체가 SQL 에러 (모델에 컬럼 존재) —
   [[migration-deploy-deps]] 참조.

## 다음에 적용하는 법

- 새 표준 도구(메모리·검색 등)의 전 에이전트 보급은 코드 배포 없이 **관리자 빌트인 지정**만으로.
- "LLM은 못 바꾸고 사람만 바꿀 수 있어야 한다"류 요구는 프롬프트가 아니라
  **요청 스키마/상태 접근 경로의 분리**로 풀 것.
- upsert가 암묵적으로 보존하는 컬럼이 생기면 SET 절 검사 테스트로 계약화할 것.
