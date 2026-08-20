---
title: MySQL FK 참조 테이블 collation 규칙 (errno 3780 방지)
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/db/migration/V037__create_agent_definition.sql
  - idt/src/infrastructure/agent_builder (SQLAlchemy 모델 생성 테이블)
  - idt/db/migration/V056·V057·V058·V059·V060 (동일 주의 주석이 반복 기록됨)
  - idt/db/migration/V058__create_agent_webhook_delivery.sql (COMMENT 최상위 콤마 금지)
  - idt/tests/db/test_migration_ddl_comments.py:36-52 (_split_top_level — 따옴표 미추적 결함 실측)
  - idt/db/migration/V061__create_prompt_session.sql, V062__create_prompt_version.sql (v3 — 같은 함정 재발)
confidence: 0.9
version: 3
created: 2026-07-20
updated: 2026-08-18
verified_at: 7c3ffdd
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

V056~V060이 전부 이 주의를 주석으로 다시 적고 있다 — 신규 테이블 마이그레이션의
사실상 표준 헤더다. 새 파일도 같은 주석을 복사해 남긴다.

## 같은 트리거에 걸리는 두 번째 함정 — COMMENT 안의 콤마 (v2 추가)

CLAUDE.md는 DDL에 **테이블 + 전 컬럼 COMMENT 필수**를 규정하고
`tests/db/test_migration_ddl_comments.py`가 V054 이후 파일을 검사한다.
이 검사기의 파서는 **COMMENT 문자열 안의 최상위 콤마를 컬럼 구분자로 오인**한다.

```sql
-- ❌ 파서가 깨진다
status VARCHAR(10) NOT NULL COMMENT '상태 (queued, running, success)',
-- ✅ 콤마 대신 파이프/중점 사용
status VARCHAR(10) NOT NULL COMMENT '상태 (queued | running | success)',
```

V058 헤더에 "COMMENT 문자열에 최상위 콤마 금지 — M1 함정"으로 기록돼 있다.

### 근본 원인 — 검사기의 알려진 결함 (v3 추가)

`_split_top_level()`(`test_migration_ddl_comments.py:36-52`)은 **괄호 깊이만 추적하고
따옴표 상태를 추적하지 않는다.** 그래서 `COMMENT '...(a, b)...'` 의 콤마를 컬럼
구분자로 오인해 조각을 쪼개고, 쪼개진 뒷조각에 `COMMENT` 가 없으니 **허위 위반**을
보고한다. 즉 이건 내 DDL이 틀린 게 아니라 **공유 테스트의 파서 버그**다.

V061·V062(prompt-composer)에서도 동일하게 재발했다. 대응 방침은 매번 같다 —
**공유 테스트를 고치지 않고 COMMENT 문안에서 콤마를 뺀다.** 파서를 고치면 V054 이후
전 마이그레이션의 검사 결과가 한꺼번에 바뀌므로 기능 사이클 안에서 건드리지 않는다
(별도 정리 사이클 대상).

증상 식별법: 위반 메시지의 `테이블.컬럼` 중 **컬럼명이 한글이거나 문장 조각**이면
파서가 COMMENT 안을 쪼갠 것이다 (실제 누락이 아님).
