# /feature

새 feature 작업 공간(worktree)과 브랜치를 생성한다.

> 상세 규칙은 `.claude/skills/git-workflow/SKILL.md` 의 **`## 0. 작업 공간 준비`** 참조.

## 사용법
```
/feature <description>
/feature <description> --here      # worktree 없이 현재 폴더에서 브랜치만 생성
```

예시:
```
/feature user-auth
/feature fix/login-redirect
/feature agent-webhook --here
```

## 실행 순서

### 1. 기본 브랜치(`<BASE>`) 감지

```bash
git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'
```

- 결과를 이후 모든 명령의 `<BASE>`로 사용한다. **`main`으로 하드코딩하지 않는다**
  (이 저장소는 `master`다).
- 실패 시 → `git remote set-head origin -a` 로 복구 후 재실행.
  그래도 실패하면 사용자에게 기본 브랜치를 묻는다.

### 2. 현재 상태 확인

```bash
git status
git worktree list
```

- `git worktree list`로 **이미 열려 있는 작업 공간**을 파악한다. 이게 곧 진행 중인 feature 목록이다.
- 미커밋 변경이 있으면 사용자에게 확인 (stash 또는 commit 먼저 할지).
  - worktree 모드에서는 메인 폴더의 미커밋 변경이 새 worktree에 **따라가지 않는다.**
    "메인 폴더에 미커밋 변경 N개가 남아 있습니다"라고 알리고, 그대로 둘지 확인한다.

### 3. 브랜치명 결정

- `<description>`에 type prefix가 없으면 `feature/`를 자동으로 붙인다
- `fix/login`처럼 type이 명시된 경우 그대로 사용

### 4. 중복 확인

```bash
git branch --list <branch>
git branch -r --list origin/<branch>
git worktree list
```

- **worktree가 이미 있으면** → 그 경로를 알려주고 종료:
  ```
  ℹ️ <branch> 는 이미 ../wt/<name> 에서 작업 중입니다.
  해당 폴더에서 Claude Code 세션을 여세요.
  ```
- **브랜치만 존재하면(worktree 없음)** → 사용자에게 확인:
  ```
  ⚠️ <branch> 브랜치가 이미 존재합니다.
  이전 작업이 아직 머지되지 않았을 수 있어요.

  A) 기존 브랜치로 worktree를 만들어 이어서 작업
  B) 다른 이름으로 새로 생성 (예: <branch>-2)
  C) 취소

  어떻게 할까요?
  ```
  - **A 선택 시**: `-b` 없이 worktree 생성 후 상태 요약
    ```bash
    git worktree add ../wt/<name> <branch>
    git log --oneline <BASE>..<branch>
    ```
  - **B 선택 시**: 새 이름을 입력받아 5번으로
  - **C 선택 시**: 종료

### 5. 작업 공간 + 브랜치 생성

**기본 (worktree 모드)** — 리포지토리 루트 기준으로 실행:

```bash
git fetch origin <BASE>
git worktree add ../wt/<name> -b <branch> origin/<BASE>
```

- `<name>`은 브랜치명에서 type prefix를 뺀 짧은 이름
- `origin/<BASE>`를 기점으로 삼으므로 **브랜치 전환 없이 최신 상태**에서 시작한다

**`--here` 지정 시 (단일 폴더 모드)** — 다른 세션이 돌고 있지 않을 때만:

```bash
git switch <BASE>
git pull origin <BASE>
git switch -c <branch>
```

- 실행 전 `git worktree list`에 다른 작업 공간이 있으면 **경고하고 확인을 받는다**
- conflict 발생 시 → **작업 중단, 사용자에게 알리고 대기**
  ```
  ⚠️ git pull 중 conflict가 발생했습니다. 직접 해결이 필요합니다.
  SKILL.md의 "Conflict 해소" 섹션을 참고하세요.
  해결 완료 후 "해결했어"라고 알려주시면 이어서 진행합니다.
  ```

### 6. 셋업 안내 (worktree 모드만, 최초 1회)

새 worktree에는 의존성과 `.env`가 없다. 다음을 **안내**한다
(사용자가 새 폴더에서 세션을 열어야 하므로 여기서 대신 실행하지 않는다):

```
✅ 작업 공간 생성 완료: ../wt/<name>  (브랜치: <branch>)

새 폴더에서 Claude Code 세션을 열고, 최초 1회만 아래를 실행하세요:

  cd ../wt/<name>/idt && uv sync

  # 프론트 작업이 필요하면 (idt_front 에서, PowerShell)
  New-Item -ItemType Junction -Path .\node_modules `
    -Target C:\Users\tkdrb\project\agent\agent\idt_front\node_modules

  # .env 복사 (gitignore라 자동으로 따라오지 않음)
  #   idt/.env, idt_front/.env.local  ← 메인 폴더에서 복사 후 포트를 다르게 수정

작업이 끝나면 /commit → /pr, 머지 후 정리:
  git worktree remove ../wt/<name>
```

- `package-lock.json`을 변경할 예정이면 junction 대신 `npm ci`를 쓰도록 함께 안내한다.

### 6-b. 완료 메시지 (`--here` 모드)

```
✅ 브랜치 생성 완료: <branch>  (현재 폴더)
이제 작업을 시작하세요. 완료되면 /commit 으로 커밋하세요.
```

## 주의

- **다른 세션이 사용 중인 워킹트리에서 브랜치를 전환하지 않는다.** 미커밋 작업이 유실된다.
- `git worktree add` 는 대상 폴더가 이미 존재하면 실패한다. 경로 충돌 시 이름을 바꿔 재시도한다.
- worktree 생성은 되돌리기 쉽다: `git worktree remove <path>` (미커밋 변경이 있으면 거부됨).
