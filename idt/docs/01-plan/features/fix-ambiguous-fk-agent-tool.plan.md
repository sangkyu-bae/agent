# Plan: fix-ambiguous-fk-agent-tool

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | AgentDefinitionModel.tools relationship AmbiguousForeignKeysError 수정 |
| 작성일 | 2026-05-15 |
| 예상 소요 | 10분 |
| 난이도 | Low |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | `agent_tool` 테이블이 `agent_definition.id`를 참조하는 FK가 2개(`agent_id`, `ref_agent_id`)이므로 SQLAlchemy가 join 조건을 자동 추론할 수 없어 서버 시작 시 seed_default_models 실패 |
| **Solution** | `AgentDefinitionModel.tools` relationship에 `foreign_keys` 인자를 명시하여 어느 FK 경로를 사용할지 지정 |
| **Function UX Effect** | 서버가 정상 부팅되고 seed_default_models가 오류 없이 실행됨 |
| **Core Value** | Agent Builder 기능의 기반 모델 관계가 올바르게 매핑되어 전체 서비스 안정성 확보 |

---

## 1. 문제 분석

### 1.1 에러 메시지

```
sqlalchemy.exc.AmbiguousForeignKeysError: Could not determine join condition
between parent/child tables on relationship AgentDefinitionModel.tools
- there are multiple foreign key paths linking the tables.
Specify the 'foreign_keys' argument.
```

### 1.2 근본 원인

`AgentToolModel`에서 `agent_definition.id`를 참조하는 ForeignKey가 **2개** 존재:

| 컬럼 | FK 대상 | 용도 |
|------|---------|------|
| `agent_id` | `agent_definition.id` | 이 도구가 소속된 에이전트 (1:N 소유 관계) |
| `ref_agent_id` | `agent_definition.id` | worker가 다른 에이전트를 참조하는 경우 (multi-agent composition) |

SQLAlchemy는 두 테이블 사이에 FK 경로가 1개일 때만 자동 join 추론이 가능하다. 2개 이상이면 `foreign_keys` 인자를 **반드시** 명시해야 한다.

### 1.3 현재 상태

- `AgentToolModel.agent` relationship → `foreign_keys=[agent_id]` **이미 명시됨** (line 80)
- `AgentDefinitionModel.tools` relationship → `foreign_keys` **누락** (line 41-46)

역방향(`back_populates`)도 `foreign_keys`가 필요한데, 한쪽만 지정하고 반대쪽은 빠트린 상태.

---

## 2. 해결 방안

### 2.1 수정 대상

| 파일 | 위치 | 수정 내용 |
|------|------|-----------|
| `src/infrastructure/agent_builder/models.py` | Line 41-46 | `AgentDefinitionModel.tools` relationship에 `foreign_keys` 추가 |

### 2.2 수정 코드

**Before:**
```python
tools: Mapped[list["AgentToolModel"]] = relationship(
    "AgentToolModel",
    back_populates="agent",
    cascade="all, delete-orphan",
    order_by="AgentToolModel.sort_order",
)
```

**After:**
```python
tools: Mapped[list["AgentToolModel"]] = relationship(
    "AgentToolModel",
    back_populates="agent",
    cascade="all, delete-orphan",
    order_by="AgentToolModel.sort_order",
    foreign_keys="[AgentToolModel.agent_id]",
)
```

### 2.3 왜 `agent_id`인가?

- `tools` relationship은 "이 에이전트가 **소유한** 도구 목록"을 의미
- `agent_id`가 소유 관계를 나타내는 FK
- `ref_agent_id`는 multi-agent composition에서 worker 참조용이므로 별개의 관계

---

## 3. 영향 범위

### 3.1 직접 영향

- `seed_default_models()` 정상 실행 → 서버 부팅 성공
- `AgentDefinitionModel.tools` eager/lazy loading 정상 동작

### 3.2 간접 영향 (확인 필요)

| 확인 항목 | 파일 | 이유 |
|-----------|------|------|
| agent_definition_repository | `src/infrastructure/agent_builder/agent_definition_repository.py` | tools relationship 사용하는 쿼리 |
| create_agent_use_case | `src/application/agent_builder/create_agent_use_case.py` | agent + tools 함께 생성 |
| run_agent_use_case | `src/application/agent_builder/run_agent_use_case.py` | tools 로딩하여 실행 |

### 3.3 변경하지 않는 것

- DB 스키마 변경 없음 (DDL 수정 불필요)
- `ref_agent_id` FK는 그대로 유지 (multi-agent composition 용도)
- `AgentToolModel.agent` relationship 변경 없음 (이미 `foreign_keys` 명시됨)

---

## 4. 검증 계획

1. 서버 시작하여 `seed_default_models` 에러 없이 통과하는지 확인
2. Agent 생성 API (`POST /api/agent-builder/agents`) 정상 동작 확인
3. Agent 조회 시 tools 목록이 올바르게 로딩되는지 확인

---

## 5. 체크리스트

- [ ] `AgentDefinitionModel.tools`에 `foreign_keys` 추가
- [ ] 서버 부팅 테스트 (seed 통과 확인)
- [ ] Agent CRUD API 동작 확인
