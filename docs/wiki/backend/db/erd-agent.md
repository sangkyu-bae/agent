---
title: 미니 ERD — 에이전트 도메인 (definition/tool/subscription/memory)
status: draft
source_type: conversation
source_refs:
  - idt/src/infrastructure/agent_builder/models.py
  - idt/src/infrastructure/agent_builder/subscription_model.py
  - idt/src/infrastructure/memory/models.py
  - idt/db/migration/V050__create_agent_memory.sql
confidence: 0.9
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

구조는 SQLAlchemy 모델에서 도출(2026-07-21 기준). 실선=실제 FK, 점선=FK 없는 소프트 참조.

```mermaid
erDiagram
    llm_model ||--o{ agent_definition : "llm_model_id (RESTRICT)"
    departments |o--o{ agent_definition : "department_id (SET NULL)"
    agent_definition ||--o{ agent_tool : "agent_id (CASCADE)"
    agent_definition |o--o{ agent_tool : "ref_agent_id (SET NULL, sub-agent)"
    agent_definition ||--o{ user_agent_subscription : "agent_id (CASCADE)"
    agent_definition |o..o{ agent_definition : "forked_from (soft)"
    users |o..o{ agent_memory : "user_id (soft, string)"

    agent_definition {
        string id PK
        string user_id "소유자 (soft ref)"
        string llm_model_id FK
        string visibility "private|department|public"
        string department_id FK
        int max_iterations "V045"
        bool include_user_context "V028"
        string forked_from "soft ref"
    }
    agent_tool {
        string id PK
        string agent_id FK
        string tool_id "저장 표기 네임스페이스"
        string worker_id "UQ(agent_id, worker_id)"
        string worker_type "tool|agent"
        string ref_agent_id FK
        json tool_config
    }
    user_agent_subscription {
        string id PK
        string user_id "UQ(user_id, agent_id)"
        string agent_id FK
        bool is_pinned
    }
    agent_memory {
        bigint id PK
        string scope "user|org"
        string user_id "org면 NULL 아님·부서id 슬롯"
        smallint tier
        string mem_type
        string status "active|pending|..."
        string source_run_id "soft ref ai_run"
        datetime expires_at
    }
```

## 각주 (코드에 안 보이는 규칙)

- **`agent_tool.tool_id`는 저장 표기다** (`{id}`, `mcp_{srv}`). 카탈로그/폼 표기(`internal:{id}`, `mcp:{srv}:{tool}`)와 다르므로 이 테이블 값을 그대로 UI에 내보내면 안 된다 ([[router-map]] 계약 주의).
- **`forked_from`은 FK가 아니다** — 원본 삭제 시에도 포크 이력 문자열은 남는다.
- **`agent_memory`는 FK가 전혀 없다** (V050 주석: V037 선례 — [[mysql-fk-collation]]). `user_id` 컬럼은 org scope에서 부서 식별자 슬롯으로 재사용되므로, 조회 시 **scope 가드 없이 user_id만으로 필터하면 부서 메모리가 새어 나간다** (agent-memory-org-scope 교훈).
- `agent_memory.status`는 승인 게이트 상태 머신이다: 추출 후보=pending → 승인 시 active (agent-memory-extraction). 행 존재≠주입 대상.
- Phase 2/3 컬럼(scope/tier/status/source_run_id/confidence/expires_at)은 V050에서 **선반영**되어 이후 마이그레이션 0으로 진행됐다 — 확장 예정 컬럼 선반영 패턴의 선례.
- 관련 테이블: `agent_schedule`/`agent_schedule_run`(V038), `agent_skill`(V034) — 에이전트 id 참조 방식은 각 모델 파일 확인.
