---
title: git worktree 수명주기 (Windows) — 셋업·node_modules Junction·머지 후 일괄 정리
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - 2026-11-14 세션 — 머지된 worktree 일괄 정리 실행·성공 (정리 후 `git worktree list` = master 1개, 로컬 브랜치 master만, verified_at 시점)
  - gh pr view 84/86/90 --json state → 3건 모두 MERGED (2026-11-03·11-03·11-04 머지, 진행 기록상은 "머지 대기"였음)
  - docs/archive/2026-11/sidebar-agent-list/sidebar-agent-list.report.md:161 (worktree 정리 전 `idt_front/node_modules` junction 먼저 제거)
  - idt/docs/archive/2026-11/agent-token-limit/agent-token-limit.report.md:192,211 (마이그레이션 번호는 다른 worktree 미커밋 파일까지 확인 · junction 제거 → worktree remove → 브랜치 삭제)
  - docs/archive/2026-11/wizard-template-request/wizard-template-request.report.md:164,176 (worktree 셋업 항목·vitest 메모리 부족 중단)
  - idt/docs/04-report/negative-feedback-drilldown.report.md:56,235 (junction이 Vite 허용 경로 밖 → 폰트 403)
  - ~/.claude/projects/.../memory/wizard-template-request-progress.md (git-bash ln -s 깊은 복사·고아 vitest가 worktree 삭제 차단 — 실측 기록)
  - ~/.claude/projects/.../memory/agent-kb-quick-setup-progress.md (master 체크아웃 untracked docs가 pull 차단·autocrlf 표시)
  - ~/.claude/projects/.../memory/local-only-deploy-files.md (git clean 금지 — settings deny)
confidence: 0.8
version: 1
created: 2026-11-14
updated: 2026-11-14
verified_at: 2fc45c5
---

> 읽는 시점: **기능 작업용 worktree(`../wt/<이름>`)를 새로 만들 때, PR 머지 후 worktree·브랜치를 정리할 때,
> `git worktree remove`가 실패하거나 `--force`를 쓰고 싶어질 때, 진행 기록에 "PR 머지 대기"라고 적힌 작업을 이어받을 때.**

## 문제

- 이 저장소는 기능마다 `C:\Users\tkdrb\project\agent\wt\<이름>` worktree를 쓴다. 프론트 `node_modules`는 매번 설치하지 않고 master 체크아웃 것을 링크하는데, 링크 방식·삭제 순서를 틀리면 **원본 `node_modules`가 지워지거나** 디스크가 깊은 복사본으로 찬다.
- `.bkit/` 런타임 파일이 항상 수정 상태라 `git worktree remove`가 거부되고 `--force`가 필요하다. `--force`는 진짜 미커밋 작업도 함께 날리므로 사전 검증 없이 쓰면 위험하다.
- 진행 메모·보고서의 "PR 머지 대기"는 시간이 지나면 틀린다(2026-11-14: #84·#86·#90이 기록상 대기였으나 실제로는 전부 MERGED).

## 검증된 사실

### 셋업
- git-bash `ln -s`는 Windows에서 **디렉터리를 깊은 복사**한다(링크가 아님). `node_modules` 링크는 PowerShell `New-Item -ItemType Junction -Path <wt>\idt_front\node_modules -Target <master>\idt_front\node_modules`로 만든다.
- 백엔드 worktree는 `uv sync --all-extras --dev`(또는 `--extra dev`), `idt/.env`·`idt/samples/` 복사가 필요하다.
- Junction 경로는 Vite `server.fs.allow` 밖이라 worktree dev 서버에서 Pretendard 폰트가 403 난다(기능 무관 콘솔 오류로 분류).
- **마이그레이션 번호는 다른 worktree의 미커밋 파일까지** 확인해 고른다(`ls ../wt/*/idt/db/migration`) — 병렬 feature 간 V084 충돌을 이렇게 잡았다([[migration-deploy-deps]]).
- worktree에서 커밋한 문서가 master 체크아웃에 untracked 사본으로 남아 있으면 master `git pull`이 거부된다 → `git show origin/master:<path> | diff -q - <path>`로 동일 확인 후 사본을 지우고 pull.

### 머지 후 정리 — 검증 → 링크 해제 → 제거 순서 (2026-11-14 실행·성공)
각 worktree마다 아래 4개가 전부 통과해야 `--force` 제거 대상이다.

| 확인 | 명령 | 통과 조건 |
|---|---|---|
| 미커밋 변경 | `git -C <wt> status --short` 에서 `.bkit/` 줄 제외 | 0건 |
| 미푸시 커밋 | `git log origin/<branch>..<branch> --oneline` | 0건 |
| master 미반영 커밋 | `git log origin/master..<branch> --oneline` | 0건 (이 저장소는 PR을 merge commit으로 머지하므로 성립 — 예: 2fc45c5) |
| PR 실제 상태 | `gh pr list --head <branch> --state all` 또는 `gh pr view <n> --json state` | `MERGED` |

1. `<wt>\idt_front\node_modules`가 Junction이면 **먼저 링크만 끊는다**: `cmd /c rmdir <wt>\idt_front\node_modules` (`rmdir`은 /s 없이 쓰면 Junction 자체만 제거하고 대상은 건드리지 않음 — 원본 보존 확인함). 링크를 남긴 채 worktree를 지우면 삭제가 링크를 따라가 **원본 `node_modules`가 지워질 위험**이 있다.
2. `git worktree remove --force <wt>` (`.bkit/` 때문에 `--force` 필요 — 그래서 위 검증이 선행 조건).
3. 삭제가 "파일 사용 중"으로 실패하면 경로를 쥔 프로세스를 찾는다: PowerShell `Get-CimInstance Win32_Process | Where-Object CommandLine -like '*<wt 이름>*'`. 실사례는 메모리 부족으로 죽은 **vitest 고아 프로세스가 네이티브 `.node` 바이너리를 잡고 있던 것**(`Stop-Process` 후 삭제 성공).
4. `git worktree prune`.
5. 로컬 브랜치는 `git branch -d <branch>` — 미머지 브랜치는 거부되므로 마지막 안전망 역할을 한다. `-D`로 우회하지 않는다.

## 다음에 적용하는 법

- 정리·이어받기 전에 기록상 PR 상태를 믿지 말고 `gh pr view <n> --json state,mergedAt`로 **실제 상태부터 확인**한다. 진행 메모를 갱신할 때도 같은 확인 결과로 덮어쓴다.
- `--force` 제거는 위 4개 검증을 통과한 worktree에만 쓴다. 하나라도 걸리면 사용자에게 보고하고 멈춘다.
- Junction 해제는 항상 worktree 제거보다 먼저. 해제 뒤 master의 `idt_front/node_modules`가 남아 있는지 확인한다.
- `git clean`은 이 저장소에서 금지돼 있다(로컬 전용 배포 파일 보호) — 정리는 위 절차로만 한다.
