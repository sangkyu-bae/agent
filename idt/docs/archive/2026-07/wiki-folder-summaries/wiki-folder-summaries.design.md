# wiki-folder-summaries Design

> **Status**: draft
> **Created**: 2026-07-25
> **Plan**: docs/01-plan/features/wiki-folder-summaries.plan.md
> **선행**: wiki-agentic-navigation (archive, Match 100%) — 본 설계는 그 위에 폴더 계층을 얹는다

---

## 1. 설계 결정 (Plan §5 확정)

### D1. 저장 모델 — 신규 테이블 `wiki_folder_summary` (V053)

wiki_article 특수 행 방식은 기각 — 폴더 요약은 승인 게이트·출처 불변식(source_refs)·
버전 관리가 없는 **파생 데이터**라 문서와 라이프사이클이 다르다.

```sql
-- V053__create_wiki_folder_summary.sql
-- wiki-folder-summaries: 쓰기 시점 폴더 요약 계층 (wiki_article path 파생 데이터).
-- FK/COLLATE 명시 없음 (V037 주석 선례), ENGINE=InnoDB.
CREATE TABLE wiki_folder_summary (
    id            CHAR(36)     NOT NULL COMMENT 'UUID PK',
    agent_id      CHAR(36)     NOT NULL COMMENT '소속 에이전트 (agent_definition.id)',
    path          VARCHAR(255) NOT NULL COMMENT '가상 폴더 경로("여신/한도"), 깊이<=3 — wiki_article.path와 동일 제약',
    summary       TEXT         NOT NULL COMMENT 'LLM 증류 폴더 안내 설명 (탐색 힌트 — 진실은 wiki_list 실시간 목록)',
    article_count INT          NOT NULL DEFAULT 0 COMMENT '하위 전체(재귀) 승인+미만료 문서 수',
    updated_at    DATETIME     NOT NULL COMMENT '마지막 재증류 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_wiki_folder (agent_id, path),
    KEY idx_wiki_folder_agent (agent_id)
) ENGINE=InnoDB
  COMMENT='에이전트 위키 폴더 요약 — 승인/편집/폐기 이벤트로 재증류되는 파생 캐시';
```

> **DDL comment 규칙 (2026-07-25 사용자 지시)**: 테이블 생성 시 **모든 컬럼과
> 테이블에 COMMENT를 항상 부여**한다 (기존 V050/V052는 비자명 컬럼만 — 이후 신규
> 테이블은 전 컬럼 필수). SQLAlchemy 모델에도 `comment=` 파라미터로 동일 반영.

- 도메인: `WikiFolderSummary` dataclass (`domain/wiki/entity.py`에 추가 — id, agent_id,
  path, summary, article_count, updated_at). 파생 데이터라 상태 전이 메서드 없음
- 저장 계약: **신규 인터페이스** `WikiFolderSummaryRepository`
  (`application/repositories/wiki_folder_repository.py` — 신규 파일, 기존
  WikiArticleRepository 페이크 무영향): `upsert(summary)`, `delete(agent_id, path)`,
  `list_by_agent(agent_id)` — 전부 request_id 수반.
  직속 하위 폴더 선별은 repo 메서드가 아니라 **호출 측 prefix 필터**(서비스
  `_load_children` / 도구 `_is_direct_child`)로 한다 — 에이전트당 폴더 수가 작아
  (깊이≤3) SQL LIKE 이중 조건보다 단순성이 이득 (as-built 0.2 정정)
- 인프라: `infrastructure/wiki/folder_summary_repository.py` + `models.py`에
  `WikiFolderSummaryModel` 추가. upsert는 MySQL `INSERT ... ON DUPLICATE KEY UPDATE`
  (SQLAlchemy dialect insert) — 동시 재증류 경합에서 마지막 쓰기 승리로 충분(파생 데이터)

### D2. 재증류 트리거 — WikiFeedbackService 팬아웃 패턴 재사용 (fire-and-forget)

`WikiFolderSummaryService` (`application/wiki/folder_summary_service.py`):

```
kickoff_refresh(agent_id, paths: list[str|None], request_id) -> None   # 동기, 즉시 반환
  ├─ enabled=False → no-op                        (config 게이트)
  ├─ asyncio.create_task(_run_guarded(...))       # WikiFeedbackService §패턴 동일
  │    └─ 실패는 warning 로그 — 승인/편집 API에 영향 0
  └─ drain()                                      # 테스트·종료 훅 전용
_refresh(agent_id, paths, request_id):
  1. 대상 경로 집합 확장: 각 path의 자기+조상 전부 (깊이≤3 → 경로당 최대 3개)
     path=None(미분류)는 요약 대상 아님 — 루트 렌더에서 실시간 처리 (D5)
  2. 깊은 경로부터(bottom-up) 순서로 각 폴더:
     a. 자체 세션으로 직속 승인 문서 + 하위 폴더 요약 조회
     b. 문서 0건 + 하위 폴더 0건 → 요약 row 삭제 (폴더 소멸)
     c. FolderSummaryDistiller로 증류 → upsert (article_count = 재귀 승인 문서 수)
```

- **호출 지점 (승인 상태를 바꾸는 모든 경로 — 2개 유스케이스)**:
  - `WikiReviewUseCase`: `_to_approved`/`_to_deprecated`/`edit` 성공 후 —
    대상 paths = [article.path]
  - `WikiHumanWriteUseCase`: `create`(HUMAN은 APPROVED 직행)/`update`/`deprecate` 후 —
    update에서 path가 바뀌면 paths = [old_path, new_path] 둘 다
  - 두 유스케이스 모두 **optional 의존성**(기본 None → no-op) — agent-memory 무회귀 관례.
    기존 생성자 호출·테스트 무수정 통과
- **정합성 계약**: 팬아웃 태스크가 요청 트랜잭션 커밋보다 먼저 읽으면 1이벤트 늦은
  요약이 될 수 있다 — **허용**(eventually consistent). 근거: 요약은 탐색 힌트이고
  진실은 wiki_list의 실시간 문서 목록(Plan §6 리스크 완화). 다음 전이에서 수렴

### D3. 증류 입력 — 계층 증류 (RAPTOR식, 상향 전파)

`FolderSummaryDistiller` (`infrastructure/wiki/folder_summary_distiller.py`,
WikiDistiller 구조 복제 — llm 주입 + from_openai 팩토리 + `_coerce_text` 재사용):

- leaf 입력: 직속 승인 문서들의 `title + content[:500]`
- 중간 폴더 입력: 직속 문서(title+절단 본문) + **하위 폴더 summary들** (문서 전문 아님)
- 총 입력 20,000자 절단 (doc-extractor LLM 입력 상한 교훈)
- 시스템 프롬프트: "아래 문서들을 보유한 폴더의 안내 설명을 2~3문장으로 작성.
  무엇을 다루는 폴더인지·어떤 질문에 유용한지 중심. 개별 문서 나열 금지"
- 인터페이스 `FolderSummaryDistillerInterface`는 `application/wiki/interfaces.py`에 추가

### D4. `wiki_list` 도구 — WikiReadTool 패턴 복제

`infrastructure/wiki/wiki_list_tool.py` — `WikiListTool(BaseTool)`:

```
name = "wiki_list"
args: path: str = ""            # ""=루트. Field description: 목차의 폴더 경로
_arun(path):
  1. RunContext agent_id 부재 → FAIL_TEXT
  2. 자체 세션: 하위 폴더 요약(list_by_agent + 직속 필터) + 해당 path 직속 승인 문서(실시간) 조회
     path="" 루트: 1세그먼트 폴더들 + path=None(미분류) 문서
  3. 폴더도 문서도 0건 → FAIL_TEXT (타 에이전트/미존재 path 동일 문구 — id 오라클 차단 관례)
  4. 렌더:
     [위키 폴더: {path or "루트"}]
     ▸ 하위 폴더:
     - {child_path} — {summary} ({article_count}건)
     ▸ 문서:
     - (id: {id}) {title} — 갱신 {date}
     하단 지시: "폴더는 wiki_list로 더 들어가고, 문서는 wiki_read(id)로 열람하세요."
FAIL_TEXT = "요청한 위키 폴더를 찾을 수 없거나 비어 있습니다. 위키 지도의 폴더 경로인지 확인하세요."
```

- 문서 목록은 **항상 실시간 쿼리** — 요약 stale과 무관하게 목록은 진실 (D2 계약의 짝)
- `TOOL_REGISTRY`에 `"wiki_list"` 등록 (category 없음 → action → react agent 경로,
  카탈로그 자동 동기화는 기존 sync 루프가 처리)
- `ToolFactory`: `case "wiki_list"` — wiki_read와 동일한
  `wiki_session_factory`/`wiki_repo_builder` + folder repo builder 재사용, 부재 시 ValueError

### D5. 목차 폴더 모드 — 임계 초과 시에만 전환 (flat 무회귀)

`prompt_rendering.py`에 `render_wiki_folder_block(folders, uncategorized, max_bytes)` 추가:

```
[에이전트 지식 위키 지도]
이 에이전트의 승인 지식은 아래 폴더로 정리되어 있습니다.
관련 폴더를 wiki_list 도구로 열어 문서 목록을 확인하고, 문서는 wiki_read로 열람하세요.

- 여신/한도 — {summary} (12건)
- 여신/심사 — {summary} (8건)
- (미분류) — 폴더 미지정 문서 {n}건 (wiki_list 경로 "" 로 조회)
---
```

- `WikiTocProvider.render_block` 분기:
  ```
  items = list_searchable_tree_items(...)          # 기존 호출 유지
  if (folder_enabled and len(items) > threshold and folder_summaries 존재):
      → render_wiki_folder_block(...)              # 폴더 모드
  else:
      → render_wiki_toc_block(items, ...)          # 기존 flat (무수정)
  ```
- 최상위(1세그먼트) 폴더만 지도에 노출 — 깊이는 wiki_list로 탐색 (프롬프트 상수화)
- 폴더 요약이 하나도 없으면(증류 전·전부 실패) flat 폴백 — 기능 저하 없음
- config (additive, 기존 값 무변경): `wiki_folder_summaries_enabled: bool = False`
  (기본 off — 마이그레이션 V053 배포 선행 필요), `wiki_folder_mode_threshold: int = 30`

### D6. 워커 구성 — wiki_read 워커에 wiki_list 동봉 (이중 주입 계약 유지)

- 워커 간 왕복 없이 "지도→진입→열람" 체인이 한 react 루프에서 돌아야 한다 —
  `workflow_compiler`의 wiki_read 워커 분기에서 폴더 모드일 때
  `tools=[wiki_read, wiki_list]`로 생성 (wiki_list 미선택이어도 동봉)
- 워커 prompt = (폴더 지도 or flat 목차) + 모드별 지시:
  `_WIKI_FOLDER_WORKER_INSTRUCTION` = "위 지도에서 관련 폴더를 wiki_list로 열어
  문서 id를 찾고, wiki_read로 본문을 열람한 뒤 답하세요. 목록에 없는 내용은
  추측하지 마세요."
- supervisor prepend는 기존과 동일하게 같은 블록 주입 (D1 이중 주입 계약 보존 —
  선행 기능 test_workflow_compiler_wiki_toc에 폴더 모드 케이스 추가)
- 사용자가 wiki_list만 단독 선택한 경우: 독립 워커로 동작 (특별 처리 없음)

### D7. 관측 — 배선 0 (선행 기능 D4 재사용)

`UsageCallback.on_tool_start`가 모든 BaseTool을 `ai_tool_call`에 자동 기록 —
wiki_list 호출은 `arguments_json.path`로, 열람은 wiki_read `article_id`로 남는다.
"어느 폴더를 열어봤는가"까지 결정적 추적 가능. 신규 배선 없음.

### D8. DI 조립 (api/main.py)

```
folder_repo_builder = lambda s: MySQLWikiFolderSummaryRepository(s, logger)
folder_distiller    = FolderSummaryDistiller.from_openai(settings.openai_llm_model, ...)
folder_service      = WikiFolderSummaryService(
    session_factory, folder_repo_builder, article_repo_builder,
    folder_distiller, enabled=settings.wiki_folder_summaries_enabled, logger)
→ WikiReviewUseCase(..., folder_service=folder_service)
→ WikiHumanWriteUseCase(..., folder_service=folder_service)
→ WikiTocProvider(..., folder_repo_builder, folder_enabled, threshold)
→ ToolFactory(..., wiki_folder_repo_builder=folder_repo_builder)
```

---

## 2. FR 매핑

| FR | 결정 | 구현 위치 |
|----|------|-----------|
| FR-01 테이블+모델 | D1 | models.py, folder_summary_repository.py, V053 |
| FR-02 증류+전파 | D2, D3 | folder_summary_service.py, folder_summary_distiller.py, review/human_write 훅 |
| FR-03 wiki_list | D4 | wiki_list_tool.py, tool_registry.py, tool_factory.py |
| FR-04 폴더 모드+폴백 | D5 | prompt_rendering.py, toc_provider.py, config.py |
| FR-05 이중 주입 유지 | D6 | workflow_compiler.py |
| FR-06 관측 0 | D7 | (조립 테스트만) |
| FR-07 E2E 이월 | §5 | ops/e2e-carryover-checklist 등재 |

## 3. 구현 순서 (TDD — 각 단계 Red→Green)

1. **domain**: `WikiFolderSummary` dataclass (테스트: 생성·필드)
2. **infra-모델/repo**: WikiFolderSummaryModel + repo (upsert/delete/list_by_agent —
   컴파일된 SQL 문자열 단언, test_wiki_repository_toc 관례)
3. **infra-증류기**: FolderSummaryDistiller (fake llm — 입력 절단·계층 입력 조립 단언)
4. **app-서비스**: WikiFolderSummaryService (fake 의존 — 조상 확장·bottom-up 순서·
   0건 삭제·실패 무해성·enabled 게이트·drain)
5. **훅**: WikiReviewUseCase/WikiHumanWriteUseCase optional 주입 + kickoff 호출
   (기존 테스트 무수정 통과 확인 포함)
6. **도구**: WikiListTool (격리·오라클 차단·루트/하위/미분류 렌더)
7. **레지스트리/팩토리**: wiki_list 등록 + case 분기 (+ sync 카탈로그 테스트 1건 —
   선행 기능 갭 교훈: 전용 단언 테스트 필수)
8. **렌더/프로바이더**: render_wiki_folder_block + WikiTocProvider 분기
   (임계 이하 flat 유지·요약 0건 폴백)
9. **컴파일러**: wiki_read 워커 wiki_list 동봉 + 폴더 모드 지시
   (test_workflow_compiler_wiki_toc 확장)
10. **DI/config**: main.py 조립 + V053 작성 + ops/migration-deploy-deps 등재

## 4. 테스트 계획

- 신규: domain 1, folder repo 4±, distiller 3±, service 6±, tool 5±,
  registry/factory/sync 4±, rendering 5±, compiler 3± — 총 ~31건
- 회귀: 선행 기능 전체(flat 목차·wiki_read·review/human_write 기존 테스트) **무수정** 통과
- 실행 관례: 배치 OSError(TIME_WAIT)는 격리 재실행으로 판정

## 5. E2E 수동 시나리오 (이월 — FR-07)

전제: V053 적용, `wiki_folder_summaries_enabled=true`, 승인 위키 > threshold, path 2단 이상.

1. 문서 승인 → `wiki_folder_summary`에 해당 path+조상 row 생성/갱신 확인
2. "여신 폴더에 어떤 지식 있어?" → `ai_tool_call`에 wiki_list(path="여신") 기록
3. "○○ 기준으로 답해줘" → wiki_list → wiki_read 체인 tool_call + 답변 인용 확인
4. threshold 이하 에이전트 → 기존 flat 목차 그대로 (무회귀)
5. 문서 전부 폐기 → 폴더 요약 row 삭제 확인

## 6. 영향 범위 / 주의

- **DB 마이그레이션 1건(V053)** — 배포 시 필수 선행 (기능 플래그 off면 코드만 배포 가능)
- 기본값 off → 운영 무영향. on 전환은 E2E 확인 후
- 승인/편집 API 지연 없음 (fire-and-forget) — 단 LLM 키 미설정 환경에서 warning 로그
  누적 가능 → enabled 게이트가 1차 차단
- LangGraph create_react_agent 다중 tools 전달은 표준 경로 — 시그니처 실측은 Do 단계
  첫 작업으로 확인 (선행 기능 D1 관례)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-25 | Initial — Plan §5 결정 6건 확정 (D1~D8) | 배상규 |
| 0.2 | 2026-07-25 | As-built 정정 (Gap 분석 반영): list_children → list_by_agent+호출측 필터, FAIL_TEXT 문구, wiki_model → openai_llm_model. 코드 보강: 폴더 단위 실패 격리(_refresh_one) | 배상규 |
