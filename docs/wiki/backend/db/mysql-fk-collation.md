---
title: MySQL FK 참조 테이블 collation 규칙 (errno 3780 방지)
status: draft
source_type: conversation
source_refs:
  - idt/db/migration/V037__create_agent_definition.sql
  - idt/src/infrastructure/agent_builder (SQLAlchemy 모델 생성 테이블)
confidence: 0.9
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
reviewer:
---

## 문제

SQLAlchemy가 생성한 테이블(예: `agent_definition`)을 FK로 참조하는 마이그레이션에서
`CHARSET`/`COLLATE`를 명시하면 참조 대상 테이블과 collation이 불일치하여
**errno 3780 (FK constraint incorrectly formed)** 이 발생한다.

## 검증된 사실

- SQLAlchemy 생성 테이블은 서버 기본 collation을 따르므로, 이를 참조하는
  Flyway 마이그레이션 DDL에서 collation을 하드코딩하면 어긋난다.
- V037 마이그레이션 주석에 선례가 기록되어 있다.

## 다음에 적용하는 법

SQLAlchemy 생성 테이블을 FK로 참조하는 새 마이그레이션 작성 시:

```sql
-- ✅ ENGINE만 명시
) ENGINE=InnoDB;

-- ❌ CHARSET/COLLATE 명시 금지
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```
