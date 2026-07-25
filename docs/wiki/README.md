# 바이브 코딩 개발 위키

sangplusbot 개발 과정에서 검증된 지식(설계 결정, 함정, 패턴, 교훈)을 축적하는 파일 기반 위키.
제품의 LLM Wiki(`idt/src/domain/wiki/`) 라이프사이클 모델을 개발 프로세스에 dogfooding한 것이다.

## 왜 존재하는가

- PDCA 아카이브(`docs/archive/`)는 **사이클 단위 기록**이라 "이 주제에 대해 지금 유효한 지식"을 찾기 어렵다.
- 이 위키는 **주제 단위 최신 지식**만 유지한다. 작업 시작 전 `/wiki search`로 조회하고,
  작업 완료 후 `/wiki update`로 갱신한다.

## 문서 구조

```
docs/wiki/
├── README.md          ← 이 파일 (규칙)
├── _INDEX.md          ← 전체 트리 인덱스 (제품 위키의 /tree 에 해당)
├── backend/           ← idt/ 관련 지식
├── frontend/          ← idt_front/ 관련 지식
├── conventions/       ← 두 프로젝트 공통 규칙·패턴
└── ops/               ← 배포·마이그레이션·환경 지식
```

폴더 경로가 제품 위키의 `path`(가상 폴더)에 해당한다. 필요하면 폴더를 추가해도 되지만
`_INDEX.md`에 반드시 반영한다.

## 문서 포맷 (frontmatter)

제품 `WikiArticle` 엔티티 필드를 그대로 차용한다:

```markdown
---
title: 문서 제목 (검색 키)
status: draft | approved | deprecated
source_type: conversation | human
source_refs:
  - 근거 파일 경로, 커밋 해시, PDCA 아카이브 문서 등 (최소 1개 필수)
confidence: 0.0 ~ 1.0
version: 1
created: YYYY-MM-DD
updated: YYYY-MM-DD
verified_at: 커밋SHA  # 이 문서가 검증된 시점의 코드 기준 (drift 검사의 좌표)
reviewer: 승인자 (approved 시 필수)
---

본문 (무엇이 문제였고, 무엇이 검증된 사실이며, 다음에 어떻게 적용하는지)
```

## 불변식 (제품 위키와 동일)

1. **출처 불변식**: `source_refs`가 비어 있는 문서는 생성할 수 없다.
2. **승인 워크플로**: 에이전트가 생성·갱신한 문서는 항상 `draft`. 사람이 `/wiki approve`로
   승인해야 `approved`가 되며, 검색 시 approved가 우선 노출된다.
3. **버전**: 본문이 바뀌면 `version` +1. 에이전트가 approved 문서를 갱신하면 `draft`로 강등된다(재승인 필요).
4. **폐기**: 더 이상 유효하지 않은 지식은 삭제하지 않고 `deprecated`로 전환한다(이력 보존).
5. **검증 좌표**: 생성·갱신 시 `verified_at`에 그 시점의 HEAD 커밋을 기록한다.
   "이 문서는 어느 코드 기준으로 맞는 얘기인가"의 좌표이며, 표류 검사(`git diff <verified_at>..HEAD -- <source_refs>`)의 기준점이다.
6. **결정 번복은 새 문서로**: 사실 서술(ERD·지도류)은 덮어쓰기+version 증가로 충분하지만,
   **설계 결정이 뒤집힐 때는 기존 문서를 수정하지 않는다** — 기존 문서를 `deprecated` 처리하고
   새 문서에 "무엇으로 바꾸는가 + 이전 안을 버린 이유"를 명시한다 (ADR 불변 원칙).
   이유가 본문에 남아야 다음 세션의 LLM이 버린 안을 다시 제안하지 않는다.

## 사용법

| 명령 | 동작 |
|------|------|
| `/wiki search <주제>` | 관련 문서 검색 (작업 시작 전) |
| `/wiki update [범위]` | wiki-curator 에이전트가 최근 작업에서 초안 생성/갱신 |
| `/wiki approve <파일>` | draft → approved 승인 |
| `/wiki status` | 승인 대기(draft) 목록 |
| `/wiki deprecate <파일>` | 폐기 처리 |

갱신은 **수동 트리거만** 허용한다. 자동 갱신 훅은 없다.
