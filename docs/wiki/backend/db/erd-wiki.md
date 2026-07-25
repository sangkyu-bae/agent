---
title: 미니 ERD — 위키 도메인 (wiki_article)
status: draft
source_type: conversation
source_refs:
  - idt/src/infrastructure/wiki/models.py
  - idt/db/migration/V036__create_wiki_article.sql
  - idt/db/migration/V051__alter_wiki_article_add_path.sql
  - idt/docs/archive/2026-07/wiki-feedback-loop/wiki-feedback-loop.report.md
confidence: 0.9
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

단일 테이블 도메인. 구조는 SQLAlchemy 모델에서 도출(2026-07-21 기준). FK 없음 — 전부 소프트 참조.

```mermaid
erDiagram
    agent_definition |o..o{ wiki_article : "agent_id (soft + 예약석)"
    users |o..o{ wiki_article : "editor_id / reviewer_id (soft)"

    wiki_article {
        string id PK "검색 청크 chunk_id와 동일"
        string agent_id "실제 에이전트 id 또는 예약석"
        string title
        text content
        string source_type "conversation|human"
        json source_refs "빈 배열 금지 (출처 불변식)"
        string status "draft|approved|deprecated"
        numeric confidence
        int version
        string editor_id
        string reviewer_id
        string path "V051 가상 폴더, NULL=미분류"
    }
```

## 각주 (코드에 안 보이는 규칙)

- **`agent_id` 예약석**: 실제 에이전트 id 외에 `HUMAN`(소유자 직접 작성, wiki-user-facing)과 `CONVERSATION`(👎 피드백 환류, wiki-feedback-loop)이 들어온다. agent_id로 조인·집계할 때 예약석을 걸러야 한다.
- **출처 불변식**: `source_refs`가 빈 문서는 도메인 레벨에서 생성 불가. 반복 👎 강화(recurring-feedback-promotion)에서는 `len(source_refs)`가 곧 **지지 횟수**로 재해석된다 — refs를 정리(dedup)하면 지지 수가 깨진다.
- **승인 워크플로**: 에이전트 생성/갱신 문서는 항상 draft. 사람이 approve해야 검색에서 우선 노출. approved 문서를 에이전트가 갱신하면 draft로 강등 + version +1. 폐기는 삭제가 아니라 `deprecated` 전환(이력 보존).
- **편집 인가**: `source_type=human`인 문서만 소유자 편집 허용 (wiki-user-facing 결정). 인가 결과는 API가 `can_manage`로 내려준다.
- **검색 연결**: 위키 본문은 Qdrant에도 인덱싱되며 검색 청크의 `chunk_id` = `wiki_article.id`. 근거 배지 → `/knowledge/:articleId` 직결 ([[wiki-screens]]).
- `path`는 V051 additive — 트리 API는 이 컬럼의 접두사 그룹핑(서버 측)으로 만든다. 배포 전 V051 필수 ([[migration-deploy-deps]]).
- distill은 같은 컬렉션 재실행 시 중복 생성 대신 skip한다 (fix-wiki-distill-dedup).
