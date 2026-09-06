# /ship

feature 브랜치 생성부터 PR 생성까지 전체 플로우를 한번에 실행한다.

## 사용법
```
/ship <description>
/ship <description> --draft
```

예시:
```
/ship user-auth
/ship fix/login-redirect --draft
```

## 실행 순서

아래 단계를 순서대로 실행한다. 각 단계는 git-workflow SKILL.md를 참고한다.

### Step 0 — 실행 위치 확인 (필수)

`/ship`은 **현재 폴더에서 끝까지 진행**하는 커맨드다. 새 worktree를 만들면
코드 작업이 다른 폴더에서 이뤄져야 하므로 한 세션에서 이어갈 수 없다.

```bash
git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'   # <BASE> 감지
git worktree list
git branch --show-current
```

- **현재 폴더가 `<BASE>`를 체크아웃한 메인 폴더이고, 다른 worktree가 열려 있는 경우**
  → 병렬 작업 중이라는 뜻이다. 중단하고 안내한다:
  ```
  ⚠️ 지금은 메인 폴더(<BASE>)이고 다른 작업 공간이 열려 있습니다.
  여기서 작업하면 다른 세션과 충돌할 수 있어요.

  A) /feature <description> 로 전용 worktree를 만든 뒤 그 폴더에서 세션 열기 (권장)
  B) 그래도 여기서 진행

  어떻게 할까요?
  ```
- **이미 feature worktree 안에 있으면** → Step 1을 건너뛰고 Step 2로 간다.

### Step 1 — Branch 생성
`/feature <description> --here` 와 동일하게 실행
- `<BASE>` 최신화 후 현재 폴더에서 브랜치 생성
- conflict 발생 시 → **즉시 중단, 사용자에게 알리고 대기**
  ```
  ⚠️ Conflict가 발생했습니다. 직접 해결이 필요합니다.
  해결 완료 후 "해결했어"라고 알려주시면 이어서 진행합니다.
  ```

### Step 2 — 코드 작업 (사용자 대기)
브랜치 생성 후 사용자에게 안내:
```
✅ 브랜치 준비 완료: feature/<description>
작업을 완료하면 "작업 완료" 또는 "done"이라고 알려주세요.
```
사용자가 완료 신호를 보내면 Step 3으로 진행.

### Step 3 — Commit
`/commit` 과 동일하게 실행
- diff 분석 → 커밋 메시지 자동 생성 → 사용자 확인 → 커밋

### Step 4 — PR 생성
`/pr` 과 동일하게 실행
- push → PR 제목/본문 생성 → `gh pr create`
- `--draft` 옵션 전달 시 draft로 생성

### 완료
```
🚀 Ship 완료!
브랜치: feature/<description>
PR: https://github.com/...
```

## 중단 및 재개

- 어느 단계에서든 오류 발생 시 상황을 설명하고 중단
- 사용자가 수동으로 해결 후 다음 단계만 개별 커맨드로 실행 가능
  - 브랜치는 만들었는데 PR만 필요하면 → `/pr`
  - 커밋만 필요하면 → `/commit`
  - 병렬 작업용 폴더부터 만들어야 하면 → `/feature`