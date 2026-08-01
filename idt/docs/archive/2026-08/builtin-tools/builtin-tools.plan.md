# Builtin Tools Planning Document

> **Summary**: 에이전트 생성 시 위키(wiki_read/wiki_list) 같은 핵심 도구가 **자동으로 포함되는 "빌트인 도구" 개념**을 도입하고, 어떤 도구를 빌트인으로 둘지는 **관리자가 화면에서 등록/해제**할 수 있게 한다. 적용은 생성 시점 스냅샷(agent_tool 저장) 방식이며, 채팅(Fix 에이전트) 초안 경로에서는 LLM이 빌트인을 임의로 빼지 못하고 **사용자의 수동 해제만 허용**한다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-01
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 지식 위키(wiki_read/wiki_list)처럼 "모든 에이전트가 갖고 있어야 자연스러운" 도구도 지금은 생성 폼/채팅에서 사용자가 직접 골라야만 붙는다. 빠뜨리면 위키를 쌓아도 에이전트가 열람하지 못하고, 어떤 도구를 기본으로 줄지는 코드 수정 없이는 바꿀 수 없다 |
| **Solution** | ① `tool_catalog`에 `is_builtin` 플래그 신설(독립 additive 컬럼, V054) + 관리자 전용 토글 API/화면 ② `CreateAgentUseCase`에서 스켈레톤 구성 후 빌트인 도구를 자동 주입(모든 생성 경로 공통·중복 방지) ③ 명시적 `exclude_builtin_tool_ids` 요청 필드로만 제외 가능 — 폼에서 사용자가 직접 해제한 경우에만 전달되고, 채팅 초안 경로는 이 필드를 쓰지 않으므로 LLM이 빌트인을 뺄 수 없음 |
| **Function/UX Effect** | 신규 에이전트는 만들자마자 위키 열람/탐색이 기본 탑재. 생성 폼에는 빌트인 도구가 "기본" 배지와 함께 미리 선택되어 있고 원하면 해제 가능. 관리자는 도구 관리 화면에서 빌트인 목록을 코드 배포 없이 조정 |
| **Core Value** | "플랫폼 표준 도구"를 데이터(카탈로그 플래그)로 선언하는 확장점 — 여신 특화가 아닌 일반화 방향(USER-SCENARIOS 원칙)이며, 이후 새 표준 도구(메모리·검색 등)도 관리자 등록만으로 전 신규 에이전트에 보급 가능 |

---

## 1. Overview

### 1.1 Purpose

에이전트 생성 시 자동 포함되는 **빌트인 도구** 집합을 도입한다.
빌트인 지정의 SoT는 `tool_catalog.is_builtin`(DB)이며, 관리자(UserRole.ADMIN)만
등록/해제할 수 있다. 초기 빌트인은 `wiki_read` + `wiki_list`.

### 1.2 Background — 현행 구조

- **내부 도구 SoT는 코드** `TOOL_REGISTRY`(`src/domain/agent_builder/tool_registry.py`)이며,
  부팅 시 `SyncInternalToolsUseCase`가 `tool_catalog` 테이블로 upsert 동기화한다
  (`internal:{id}` 규약). MCP 도구는 `SyncMcpToolsUseCase`가 `mcp:{srv}:{tool}`로 동기화.
- **에이전트별 도구는 `agent_tool` 테이블**(workers)에 저장되고, 생성 경로는
  폼 직접 선택·채팅(Fix 에이전트) 초안 모두 `CreateAgentUseCase`로 수렴한다
  (`tool_ids` → `_build_skeleton_from_tool_ids`, 카탈로그 ID → 저장 ID 정규화 포함).
- wiki_read/wiki_list는 현재 사용자가 선택해야만 워커로 붙는다. 폴더 모드에서는
  `WorkflowCompiler`가 wiki_read 워커에 wiki_list를 자동 동봉한다(wiki-folder-summaries D6).

### 1.3 사용자 결정 사항 (2026-08-01 인터뷰)

| 질문 | 결정 |
|------|------|
| 적용 방식 | **생성 시 자동 추가(스냅샷)** — agent_tool에 저장, 기존 에이전트 소급 없음 |
| 소유자 opt-out | **가능하되 수동만** — 채팅 초안 경로에서 LLM이 빼는 것은 금지, 폼에서 사용자가 직접 해제하는 것만 허용 |
| 대상 범위 | **internal + MCP 모두** 빌트인 지정 가능 |
| 초기 빌트인 | **wiki_read + wiki_list** |

### 1.4 Related Documents

- `docs/wiki/_INDEX.md` — 도구/에이전트 빌더 관련 승인 문서 우선 참조
- `docs/rules/tool-and-mcp.md` — 도구 추가·변경 시 필수 규칙
- 선례: agent-tool-id-dual-namespace(카탈로그↔저장 ID 변환), 독립 opt-in 필드 선호
  (기존 필드 확장 대신 신규 bool 컬럼 — `is_builtin`이 이 원칙을 따름)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 스키마**: `tool_catalog.is_builtin` BOOL NOT NULL DEFAULT 0 컬럼 추가
      (V054, 전 컬럼 COMMENT 규칙 준수) + 초기 시드(wiki_read/wiki_list UPDATE)
- [ ] **S2. 부팅 동기화 보존**: `SyncInternalToolsUseCase`/`SyncMcpToolsUseCase`의
      upsert가 **`is_builtin`을 덮어쓰지 않도록** 보존 (신규 INSERT 시 기본값 처리는
      Design에서 확정 — 프레시 DB에서도 wiki 2종이 빌트인이 되도록)
- [ ] **S3. 관리자 API**: 빌트인 토글 엔드포인트(예: `PATCH /api/v1/tool-catalog/{id}/builtin`)
      — ADMIN 전용(비관리자 403), `GET /tool-catalog` 응답에 `is_builtin` 노출
- [ ] **S4. 생성 시 자동 주입**: `CreateAgentUseCase`에서 스켈레톤 구성 직후 빌트인
      도구 워커를 주입 — 이미 선택된 도구와 중복 방지(정규화 ID 기준), 폼/채팅 등
      모든 생성 경로 공통 적용
- [ ] **S5. 수동 opt-out**: `CreateAgentRequest.exclude_builtin_tool_ids`(신규 optional
      필드) — 명시된 빌트인만 주입에서 제외. 채팅 초안 경로는 이 필드를 설정하지
      않으므로 빌트인이 항상 포함됨
- [ ] **S6. MCP 빌트인 안전장치**: 비활성/미등록 MCP 서버의 빌트인 도구는 생성을
      실패시키지 않고 **제외 + 경고 로그** (에이전트 생성 가용성 우선)
- [ ] **S7. 프론트 — 생성 폼**: 빌트인 도구를 "기본" 배지와 함께 기본 선택 상태로
      표시, 사용자가 해제하면 `exclude_builtin_tool_ids`로 전달
- [ ] **S8. 프론트 — 관리자 도구 관리**: 도구 카탈로그 목록에서 빌트인 토글
      (ADMIN 역할에만 노출), 타입/서비스/훅 동기화 (api-contract-sync)
- [ ] **S9. 테스트**: TDD — 주입/중복 방지/opt-out/권한(403)/sync 보존 백엔드 테스트,
      폼 기본 선택·해제·관리자 토글 프론트 테스트

### 2.2 Out of Scope

- **기존 에이전트 소급 적용** — 스냅샷 방식 결정에 따름 (기존 에이전트는 수정 화면에서
  직접 추가; 일괄 백필은 필요 시 후속)
- **에이전트 수정(update) 경로의 빌트인 재주입/강제** — 수정 시 워커 제거는 현행
  수동 편집 그대로 허용 (Design에서 채팅 기반 수정 경로가 있는지 재확인만)
- 빌트인 도구의 `tool_config` 사전 구성 (wiki 2종은 config 불요 — RAG류를 빌트인화할
  때 후속 과제로)
- 사용자별/부서별 빌트인 차등 (전역 단일 집합만)
- `TOOL_REGISTRY` 구조 변경, 도구 실행 경로(WorkflowCompiler) 변경 —
  wiki_list 동봉 로직 등 기존 컴파일 동작은 그대로

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `tool_catalog.is_builtin` 컬럼(V054) + wiki_read/wiki_list 초기 시드 | High | Pending |
| FR-02 | 관리자만 빌트인 등록/해제 가능 (토글 API, 비관리자 403) — internal·MCP 모두 대상 | High | Pending |
| FR-03 | `GET /tool-catalog` 응답에 `is_builtin` 포함 (프론트 타입 동기화) | High | Pending |
| FR-04 | 에이전트 생성 시(모든 경로) 빌트인 도구가 워커로 자동 주입되고, 사용자가 이미 선택한 도구와 중복 생성되지 않는다 | High | Pending |
| FR-05 | `exclude_builtin_tool_ids`에 명시된 빌트인만 주입 제외 — 채팅 초안 경로에서는 미사용이라 LLM이 빌트인을 뺄 수 없다 | High | Pending |
| FR-06 | 부팅 도구 동기화(internal/MCP upsert)가 기존 행의 `is_builtin` 값을 보존한다 | High | Pending |
| FR-07 | 비활성/미등록 MCP 빌트인은 생성 시 제외+경고 로그, 에이전트 생성은 성공한다 | Medium | Pending |
| FR-08 | 생성 폼: 빌트인 도구 기본 선택 + "기본" 배지, 수동 해제 시 exclude로 전달 | High | Pending |
| FR-09 | 관리자 도구 관리 UI: 카탈로그 목록에서 빌트인 토글 (ADMIN에만 노출) | Medium | Pending |
| FR-10 | 도구 개수 정책(`validate_tool_count`)과 빌트인 주입의 상호작용이 정의된다 (주입 후 초과 시 동작 — Design 확정) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 빌트인 판정은 application(UseCase)에서, 저장은 infrastructure, 권한은 라우터 의존성 — 레이어 이동 없음 | verify-architecture 스킬 |
| TDD | 테스트 선행 (Red → Green), 신규 모듈 테스트 파일 존재 | verify-tdd 스킬 |
| DB | DDL 전 컬럼 COMMENT, FK/COLLATE 명시 금지 관례 준수, Repository 내 commit 금지 | 코드 리뷰 + 기존 규칙 |
| API 계약 | 백엔드 스키마 변경분 프론트 타입/서비스/훅 동기화 | api-contract-sync 체크리스트 |
| 회귀 안전 | 기존 에이전트 생성/실행 테스트 무회귀 (Windows 격리 실행 관례) | pytest 격리 실행 + vitest --pool=threads |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 관리자가 화면에서 임의 도구를 빌트인 등록/해제할 수 있다
- [ ] 신규 에이전트를 폼·채팅 어느 경로로 만들어도 wiki_read/wiki_list 워커가 붙어 있다
- [ ] 폼에서 빌트인을 해제하고 만들면 해당 워커가 없다 (채팅 경로는 해제 불가)
- [ ] 재부팅(동기화) 후에도 관리자가 지정한 빌트인 플래그가 유지된다
- [ ] 비관리자의 토글 시도는 403

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, config 하드코딩 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 부팅 sync upsert가 `is_builtin`을 0으로 덮어써 관리자 설정이 재부팅마다 증발 | High | High (현행 upsert 그대로면 확정 발생) | FR-06을 별도 요구사항으로 명시 — upsert 컬럼에서 is_builtin 제외 또는 read-modify-write, 보존 단언 테스트 필수 |
| 프레시 DB에서는 마이그레이션 UPDATE 시점에 카탈로그 행이 없어 초기 시드가 no-op | Medium | Medium | 신규 INSERT 시 기본 빌트인 처리(ToolMeta 기본값 vs 시드 마이그레이션 병행)를 Design에서 확정 |
| MCP 빌트인 서버 장애/비활성 시 전 신규 에이전트 생성 실패 | High | Medium | FR-07: 제외+로그로 격하, 생성 차단 금지 |
| 빌트인 주입으로 도구 개수 상한 초과 → 기존에 만들던 구성이 갑자기 실패 | Medium | Medium | FR-10에서 정책 확정 (빌트인은 상한 계산 제외 또는 상한 내 우선 배정) |
| wiki_list 단독 워커와 WorkflowCompiler의 wiki_read 동봉 로직이 중복 (wiki_list가 워커로도, 동봉 도구로도 존재) | Low | High | Design에서 실행 경로 점검 — 중복이어도 기능상 무해한지 확인, 유해하면 wiki_read만 빌트인+동봉 의존으로 조정 |
| 위키 문서가 없는 에이전트에 wiki 워커가 붙어 헛돌이 응답 | Low | High | 기존 워커 지시가 "위키에서 확인되지 않습니다" 폴백을 보유 — 수용, E2E에서 확인만 |
| 채팅 초안 응답에 빌트인이 노출되지 않아 사용자가 "안 붙었다"고 오인 | Low | Medium | CreateAgentResponse.workers에 주입분 포함(자동) + 프론트 초안 미리보기에 표시 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | Simple structure | ☐ |
| Dynamic | Feature-based modules | ☐ |
| **Enterprise** | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 빌트인 SoT | 코드(TOOL_REGISTRY 플래그) / DB(tool_catalog 컬럼) / 별도 테이블 | **DB 컬럼 `is_builtin`** | 관리자가 배포 없이 등록/해제해야 하므로 런타임 SoT는 DB. MCP 도구까지 포괄하려면 카탈로그가 유일한 공통 지점. 독립 additive bool — 기존 필드 확장 대신 신규 opt-in 필드 선호 원칙과 일치 |
| 적용 시점 | 실행 시 동적 주입 / **생성 시 스냅샷** / 폼 기본값만 | **생성 시 스냅샷** (사용자 결정) | agent_tool에 저장되어 에이전트 정의가 자기완결적 — 실행 경로(WorkflowCompiler) 무변경, 관측/디버깅 단순. 소급 미적용은 수용 |
| opt-out 채널 | 없음 / 요청 필드(exclude) / 사후 수정만 | **exclude_builtin_tool_ids 요청 필드** | "수동 해제만 허용" 제약의 기술적 구현 — 폼 UI만 이 필드를 만들 수 있고, 채팅 초안 프롬프트/파이프라인에는 이 필드가 존재하지 않으므로 LLM 우회 불가 (구조적 차단, 프롬프트 방어 불요) |
| 주입 위치 | 라우터 / **CreateAgentUseCase** / WorkflowCompiler | **CreateAgentUseCase** | 모든 생성 경로가 수렴하는 단일 지점 + 스냅샷 저장 직전. 컴파일러 주입은 동적 방식이라 결정과 상충 |
| 초기 시드 방법 | 마이그레이션 UPDATE / ToolMeta 기본값 / 양쪽 병행 | Design에서 확정 | 기존 DB는 UPDATE로 충분하나 프레시 DB는 sync INSERT 시점 기본값 필요 — 보존 로직(FR-06)과 함께 설계 |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── db/migration/V054__add_tool_catalog_is_builtin.sql     # S1
├── src/domain/tool_catalog/entity.py                      # is_builtin 필드
├── src/application/tool_catalog/
│   ├── sync_internal_tools_use_case.py                    # S2 보존
│   ├── sync_mcp_tools_use_case.py                         # S2 보존
│   ├── set_builtin_use_case.py (신규)                     # S3 토글
│   └── schemas.py / list_tool_catalog_use_case.py         # is_builtin 노출
├── src/infrastructure/tool_catalog/
│   ├── models.py                                          # 컬럼 추가
│   └── tool_catalog_repository.py                         # 보존 upsert + 토글
├── src/application/agent_builder/
│   ├── schemas.py                                         # exclude_builtin_tool_ids
│   └── create_agent_use_case.py                           # S4/S5/S6 주입
├── src/api/main.py + 라우터                               # S3 배선(ADMIN 가드)
└── tests/ (application/tool_catalog, agent_builder, api)  # S9

idt_front/
├── src/types + services + hooks (tool catalog)            # FR-03 동기화
├── 에이전트 생성 폼 (도구 선택 섹션)                       # S7 배지·기본선택·exclude
└── 관리자 도구 관리 화면 (신규 or 기존 확장)               # S8 토글
```

---

## 7. Convention Prerequisites

- [x] 검증 스킬: verify-architecture, verify-tdd, api-contract-sync
- [x] DDL COMMENT 필수 / FK CHARSET·COLLATE 명시 금지 관례 (메모리 기록)
- [x] 카탈로그↔저장 tool_id 이중 네임스페이스 변환 규약 (`internal:{id}`→`{id}`, `mcp:{srv}:{tool}`→`mcp_{srv}`)
- 배포 시 **V054 적용 필수** (미적용 시 카탈로그 조회 SQL 에러)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. S1/FR-01   V054 마이그레이션 + entity/models 컬럼 (테스트 선행)
2. S2/FR-06   sync 보존 테스트(Red: 현행 upsert가 플래그를 덮어씀 확인) → 보존 구현
3. S3/FR-02~03 토글 UseCase + 라우터(ADMIN 가드) + 카탈로그 응답 노출
4. S4~S6/FR-04~07 CreateAgentUseCase 주입 (중복 방지 → exclude → MCP 격하 순으로 TDD)
5. S7~S8/FR-08~09 프론트 — 타입 동기화 → 생성 폼 배지/기본선택 → 관리자 토글
6. 회귀: 백엔드 격리 pytest + 프론트 vitest --pool=threads
```

### 8.2 검증 시나리오 (수동 E2E — 이월 가능)

- 관리자로 tavily_search 빌트인 등록 → 신규 에이전트에 자동 포함 확인 → 해제 →
  이후 신규 에이전트엔 미포함, 기존 에이전트는 불변
- 채팅으로 에이전트 생성 → 위키 도구 포함 확인 (초안에서 빼달라고 해도 포함되는지)
- 폼에서 wiki_read 해제 후 생성 → 미포함 확인

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design builtin-tools`) — 초기 시드 전략(프레시 DB),
       도구 개수 상한 정책(FR-10), wiki_list 동봉 중복 점검, 관리자 UI 위치 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze builtin-tools`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-01 | Initial draft — 적용 방식(스냅샷)·opt-out(수동만)·범위(internal+MCP)·초기 시드(wiki 2종) 사용자 인터뷰 반영 | 배상규 |
