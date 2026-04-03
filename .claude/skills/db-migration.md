---
name: db-migration
description: SQLAlchemy 모델에서 DDL을 추출해 db/migration/ 폴더에 Flyway 형식(V001__create_tablename.sql)으로 마이그레이션 파일을 생성한다. 기존 마이그레이션 파일을 스캔해 신규 테이블만 감지하고 추가한다. "마이그레이션 생성", "DDL 추출", "db migration", "migration file" 언급 시 즉시 실행한다.
---

# DB Migration Skill

SQLAlchemy ORM 모델에서 MySQL DDL을 자동 추출해 `db/migration/` 에 Flyway 형식 파일을 생성한다.

---

## Step 1 — 기존 마이그레이션 파일 스캔

`db/migration/` 폴더의 파일 목록을 확인해 이미 커버된 테이블을 파악한다.

```bash
ls db/migration/
```

파일명 패턴: `V{NNN}__{action}_{tablename}.sql`
- 예: `V001__create_conversation_message.sql`

다음을 추출한다:
1. **최대 버전 번호** → 다음 파일의 시작 번호 결정
2. **이미 존재하는 테이블명** → 신규 테이블 감지에 사용

파일명에서 테이블명 추출 규칙:
- `V001__create_conversation_message.sql` → `conversation_message`
- `V002__alter_agent_definition_add_col.sql` → `agent_definition` (alter 포함)
- 파일 내부의 `CREATE TABLE \`tablename\`` 패턴으로도 검증 가능

---

## Step 2 — 모든 SQLAlchemy 모델 파일 탐색

`idt/src/infrastructure/` 아래의 모든 `models.py` 파일과 `persistence/models/` 하위 파일을 찾는다.

탐색 경로:
- `idt/src/infrastructure/persistence/models/*.py` (Base 제외)
- `idt/src/infrastructure/**/models.py`

각 파일에서 `__tablename__` 값을 추출해 **전체 테이블 목록**을 만든다.

```python
# 추출 예시
# idt/src/infrastructure/persistence/models/conversation.py
# → conversation_message, conversation_summary

# idt/src/infrastructure/agent_builder/models.py
# → agent_definition, agent_tool

# idt/src/infrastructure/mcp_registry/models.py
# → mcp_server_registry

# idt/src/infrastructure/middleware_agent/models.py
# → middleware_agent, middleware_agent_tool, middleware_config
```

---

## Step 3 — 신규 테이블 감지

**전체 테이블 목록** (Step 2) - **기존 커버 테이블** (Step 1) = **신규 테이블 목록**

신규 테이블이 없으면:
```
✅ 모든 테이블이 이미 마이그레이션 파일로 커버되어 있습니다.
   커버된 테이블: {table_list}
```
를 출력하고 종료한다.

---

## Step 4 — DDL 생성 (SQLAlchemy 자동 추출)

신규 테이블마다 아래 Python 명령으로 MySQL DDL을 생성한다.
명령은 **반드시 `idt/` 디렉토리에서** 실행한다.

```bash
cd idt && python -c "
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

# 해당 모델 임포트 (파일 경로에 맞게 변경)
from src.infrastructure.XXX.models import YYYModel

ddl = str(CreateTable(YYYModel.__table__).compile(dialect=mysql.dialect()))
print(ddl + ';')
"
```

### 임포트 경로 매핑표

| 테이블명 | 임포트 경로 |
|---------|------------|
| `conversation_message` | `from src.infrastructure.persistence.models.conversation import ConversationMessageModel` |
| `conversation_summary` | `from src.infrastructure.persistence.models.conversation import ConversationSummaryModel` |
| `agent_definition` | `from src.infrastructure.agent_builder.models import AgentDefinitionModel` |
| `agent_tool` | `from src.infrastructure.agent_builder.models import AgentToolModel` |
| `mcp_server_registry` | `from src.infrastructure.mcp_registry.models import MCPServerModel` |
| `middleware_agent` | `from src.infrastructure.middleware_agent.models import MiddlewareAgentModel` |
| `middleware_agent_tool` | `from src.infrastructure.middleware_agent.models import MiddlewareAgentToolModel` |
| `middleware_config` | `from src.infrastructure.middleware_agent.models import MiddlewareConfigModel` |

> 새 모델이 추가되면 이 표도 업데이트한다.

### ForeignKey 포함 테이블 순서 주의

ForeignKey 참조가 있는 테이블은 참조 대상 테이블 뒤에 생성해야 한다.
- `agent_tool` → `agent_definition` 이후
- `middleware_agent_tool`, `middleware_config` → `middleware_agent` 이후

---

## Step 5 — 마이그레이션 파일 작성

### 파일명 규칙

```
V{NNN}__{action}_{tablename}.sql
```

- `NNN`: 3자리 zero-padding (001, 002, ...)
- `action`: `create` (신규 테이블), `alter` (컬럼 추가/수정), `drop` (삭제)
- `tablename`: 테이블명 그대로 사용

다음 버전 번호 = 기존 최대 버전 + 1 (신규 파일마다 1씩 증가)

### 파일 헤더 형식

```sql
-- Migration: V{NNN}__create_{tablename}.sql
-- Created: {YYYY-MM-DD}
-- Description: Create {tablename} table
--
-- Table: {tablename}
-- Source: idt/src/infrastructure/{path}/models.py

{SQLAlchemy 생성 DDL};
```

### db/migration/ 폴더가 없을 경우

```bash
mkdir -p db/migration
```

---

## Step 6 — 완료 보고

```
✅ DB Migration 생성 완료

신규 감지 테이블: {N}개
  - {tablename} → V{NNN}__create_{tablename}.sql
  - ...

기존 커버 테이블: {M}개 (스킵)
  - {tablename}
  - ...

생성 위치: db/migration/
```

---

## 오류 처리

### ImportError 발생 시
- `PYTHONPATH`가 `idt/src`가 아닌 `idt/`로 설정돼야 한다
- `cd idt` 후 실행하는지 확인
- 가상환경이 활성화되지 않은 경우: `source .venv/bin/activate` 또는 `.venv\Scripts\activate`

### 새 모델 파일 추가 시 스킬 업데이트
새 `models.py` 파일이 추가되면 **Step 4의 임포트 경로 매핑표**를 업데이트한다.
`manage-skills` 스킬로 관리할 수 있다.
