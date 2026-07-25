---
name: wiki
description: 바이브 코딩 개발 위키(docs/wiki/) 조회·갱신·승인·표류검사 명령. "/wiki search <주제>", "/wiki update [범위]", "/wiki approve <파일>", "/wiki status", "/wiki deprecate <파일>", "/wiki drift [파일]", "/wiki history <파일>" 형태로 사용자가 명시적으로 호출할 때만 실행한다. 자동 트리거 금지.
---

# 개발 위키 관리 (/wiki)

`docs/wiki/`(워크스페이스 루트)의 파일 기반 개발 위키를 관리한다.
규칙과 문서 포맷은 `docs/wiki/README.md`가 원본이다.

**중요: 이 스킬은 사용자가 `/wiki ...`를 직접 입력했을 때만 실행한다. 작업 완료 후 자동으로 위키를 갱신하지 않는다.**

인자 파싱: 첫 단어가 서브커맨드(search/update/approve/status/deprecate), 나머지가 대상.
서브커맨드 없이 `/wiki <텍스트>`만 오면 search로 간주한다.

## search <주제>

작업 시작 전 관련 지식 조회.

1. `docs/wiki/`에서 주제 키워드로 Grep (제목·본문·frontmatter).
2. 매칭 문서를 status별로 정리해 보여준다: **approved 우선**, draft는 "⚠ 미승인" 표시, deprecated는 기본 제외(명시 요청 시만).
3. 매칭이 없으면 `_INDEX.md` 트리를 보여주고 "관련 문서 없음"을 명시한다.

## update [범위]

wiki-curator 서브에이전트를 Agent 도구로 스폰한다. 직접 위키를 쓰지 않는다.

- 프롬프트에 범위를 전달한다: 사용자가 지정한 기능명/파일, 없으면 "최근 작업".
- 이번 세션에서 나온 검증된 교훈이 있으면 요약해서 프롬프트에 함께 넘긴다(에이전트는 대화를 볼 수 없다).
- 에이전트 보고(생성/갱신/제외 목록)를 사용자에게 그대로 전달하고, draft 승인 방법(`/wiki approve <파일>`)을 안내한다.

## approve <파일>

1. 대상 문서를 Read하고 사용자에게 **본문 요약을 보여준 뒤** frontmatter를 수정한다:
   `status: approved`, `reviewer: <git user명>`, `updated: 오늘 날짜`.
2. `source_refs`가 비어 있으면 승인을 거부하고 출처 보강을 요구한다(출처 불변식).
3. `_INDEX.md`의 해당 항목 이모지를 📝 → ✅로 갱신한다.

## status

`docs/wiki/` 전체를 스캔해 status별 개수와 draft 목록(파일 경로 + 제목)을 표로 보여준다.

## drift [파일]

문서-코드 표류 검사. doc-drift-checker 서브에이전트를 Agent 도구로 스폰한다 (직접 검사하지 않는다).

1. 프롬프트에 대상을 전달한다: 파일 지정 시 그 문서만, 없으면 위키 전체.
2. 에이전트의 표류 리포트(🔴 표류 / 🟡 의심 / 🟢 일치 / ⚪ 좌표 없음 표)를 그대로 사용자에게 전달한다.
3. 🔴 항목에는 `/wiki update <문서>` 재추출을, ⚪ 항목에는 verified_at 기입을 안내한다.
4. 이 명령은 아무것도 수정하지 않는다 — 수정 여부는 사람이 결정한다.

## history <파일>

문서의 변경 이력 조회 (git이 원장 — 문서 안에 changelog를 두지 않는다).

1. `git log --follow --format='%h %ad %s' --date=short -- <파일>` 결과를 표로 보여준다.
2. 특정 시점 상세 요청 시 `git show <해시> -- <파일>`로 diff를 보여준다.

## deprecate <파일>

1. frontmatter를 `status: deprecated`, `updated: 오늘 날짜`로 수정한다. 파일은 삭제하지 않는다.
2. `_INDEX.md` 이모지를 🗑로 갱신한다.
3. 대체 문서가 있으면 본문 상단에 `> 대체: [새 문서](경로)` 인용을 추가한다.
