---
name: git-workflow
description: >
  Claude Code에서 feature 작업 시 작업 공간(worktree) 준비 → branch 생성 → 코드 작업
  → commit → PR 생성까지 전체 git 워크플로우를 일관되게 수행하는 skill.
  GitHub (gh CLI) 기반이며 Conventional Commits 컨벤션을 따른다.
  여러 feature를 동시에 진행할 때 작업분이 서로 덮어쓰이는 것을 worktree로 방지한다.
  다음 상황에서 반드시 이 skill을 사용하세요:
  - "feature 따줘", "브랜치 만들어줘", "PR 보내줘", "커밋해줘" 등 git 작업 요청
  - 기능 구현 후 "이제 올려줘", "push해줘" 라고 할 때
  - "작업 시작해줘", "이슈 작업 시작" 등 새 작업 착수 시
  - "동시에 작업", "병렬로", "worktree", "다른 작업도 같이" 등 병렬 작업 요청
  - 코드 변경이 완료되어 리뷰 요청이 필요할 때
---

# Git Workflow Skill

GitHub + Conventional Commits 기반의 전체 git 워크플로우를 담당한다.

---

## 전체 플로우 요약

```
0. 작업 공간 준비   →  git worktree add ../wt/<name> -b <branch> <BASE>
1. branch 생성      →  (0에서 함께 생성됨 / 슬롯 모드는 git switch -c)
2. 코드 작업        →  (Claude Code가 파일 수정)
3. 변경사항 확인    →  git status / git diff
4. stage & commit   →  git add . && git commit -m "..."
5. push             →  git push -u origin <branch>
6. PR 생성          →  gh pr create --base <BASE>
7. 정리             →  git worktree remove ../wt/<name>
```

---

## ⚠️ 시작 전 — 기본 브랜치(`<BASE>`) 확인

이 문서의 `<BASE>`는 **하드코딩된 `main`이 아니라 감지한 값**이다.
git 명령을 만들기 전에 **반드시 한 번 실행해서** 결과를 `<BASE>`에 대입한다.

```bash
git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'
```

- 이 저장소(sangplusbot)의 현재 값은 **`master`** 이다. `main`이 아니다.
- 위 명령이 실패하면 → `git remote set-head origin -a` 로 복구 후 재실행
- 그래도 실패하면 → 사용자에게 기본 브랜치를 묻는다. **추측해서 `main`을 쓰지 않는다.**

---

## 0. 작업 공간 준비 (병렬 작업의 전제)

### 왜 필요한가

CC 세션 2개가 **같은 폴더**를 보고 있으면 브랜치를 나눠도 소용없다.
파일시스템은 하나라서 **마지막 저장이 이기고**, 한쪽이 `git switch`를 하는 순간
다른 쪽의 미커밋 작업이 오염된다. `git worktree`는 `.git`을 공유하면서
**폴더만 분리**하므로 이 충돌이 물리적으로 불가능해진다.

> **철칙: 워킹트리 1개 = 브랜치 1개 = CC 세션 1개.**
> 다른 세션이 쓰고 있는 폴더에서 `git checkout` / `git switch`를 실행하지 않는다.

### 폴더 레이아웃

```
project\agent\
├── agent\          ← <BASE> 전용. 여기서 feature 작업 금지 (최신화·머지 전용)
└── wt\
    ├── <feature-a>\
    └── <feature-b>\
```

### 모드 A — 신규 worktree (기본)

새 feature를 시작할 때. 브랜치 생성이 여기 포함된다.

```bash
git -C <repo-root> worktree add ../wt/<name> -b <type>/<description> <BASE>
```

- `<name>`은 짧게 (브랜치명이 길면 축약). 폴더명이 곧 "진행 중인 작업 목록"이 된다.
- 기존 브랜치를 이어서 작업할 때는 `-b` 없이:
  `git worktree add ../wt/<name> <type>/<description>`

### 모드 B — 슬롯 재사용 (feature 회전이 빠를 때)

`wt/slot1`, `wt/slot2` 처럼 상설 폴더를 두고 그 안에서 브랜치만 교체한다.
`.venv` / `node_modules`는 gitignore라 브랜치 전환에 영향받지 않으므로 **셋업이 0회**다.

```bash
# 해당 슬롯을 쓰는 세션에서만 실행할 것
git switch <BASE> && git pull origin <BASE>
git switch -c <type>/<description>
```

### 모드 C — 단일 폴더 (레거시)

worktree 없이 메인 폴더에서 직접 작업. **다른 세션이 동시에 돌고 있지 않을 때만** 허용.
이때는 `## 1. Branch 생성`의 명령을 쓴다.

### worktree 생성 후 셋업 (최초 1회)

새 worktree는 소스만 있고 의존성이 없다. 아래를 순서대로 안내한다.

| 항목 | 명령 | 비고 |
|------|------|------|
| 백엔드 의존성 | `cd <wt>/idt && uv sync` | uv 캐시에서 하드링크 — 수 초 |
| 프론트 의존성 | `node_modules`를 메인에서 junction | 아래 참조 |
| 환경변수 | `idt/.env`, `idt_front/.env.local` 을 메인에서 복사 | gitignore라 자동으로 안 따라옴 |
| 포트 | 복사한 `.env`의 포트를 worktree마다 다르게 수정 | 8000/5173 충돌 방지 |

```powershell
# node_modules junction (관리자 권한 불필요)
New-Item -ItemType Junction -Path .\node_modules `
  -Target C:\Users\tkdrb\project\agent\agent\idt_front\node_modules
```

**junction 사용 시 지켜야 할 3가지**
1. `package-lock.json`을 바꾸는 feature는 junction을 풀고 진짜 `npm ci`를 한다
   (worktree에서 `npm install`을 하면 **메인 `node_modules`가 실제로 변경**되어 다른 worktree까지 오염됨)
2. `vite.config.ts`에 `cacheDir: '.vite'`가 없으면 두 dev 서버가 같은 최적화 캐시를 덮어쓴다
3. 두 worktree에서 `npm` 명령을 **동시에** 돌리지 않는다 (읽기 전용인 `npm run dev`, `vitest`는 동시 실행 안전)

### 작업이 끝나면 정리

PR이 머지된 뒤에 실행한다. **순서를 지켜야 한다.**

```powershell
# ① node_modules junction 을 먼저 제거 (리파스 포인트만 삭제, 대상은 보존)
[System.IO.Directory]::Delete("<wt>\idt_front\node_modules", $false)
```
```bash
# ② 그 다음에 worktree 제거
git worktree remove ../wt/<name>
git worktree prune                   # 수동으로 폴더를 지웠을 때 메타데이터 정리
git branch -d <type>/<description>   # 머지된 브랜치 삭제
```

> 🚨 **junction을 남긴 채 폴더를 지우지 않는다.** 삭제 도구가 링크를 따라 들어가면
> **메인의 `node_modules`까지 지워질 수 있다.** `Remove-Item -Recurse` 도 같은 이유로 위험하다.
> 위 `[System.IO.Directory]::Delete($path, $false)` 는 링크 자체만 지운다 (실측 확인).

- `git worktree list` 로 현재 열린 작업 공간을 확인한다.
- **`git worktree remove` 는 gitignore된 파일(`.venv` 등)을 말없이 함께 지운다.**
  거부되는 건 *추적 중인 파일에 미커밋 변경이 있을 때*뿐이다 —
  "거부되지 않았으니 안전하다"고 단정하지 말고, 실행 전에 `git status`를 확인한다.
- 거부되면 `--force`로 밀지 말고 사용자에게 알린다.

### 병렬 작업 시 여전히 남는 충돌 지점

worktree는 **코드만** 격리한다. 아래는 실제 인스턴스가 하나뿐이므로 조율이 필요하다.

| 자원 | 대응 |
|------|------|
| MySQL 스키마 | 마이그레이션을 건드리는 feature끼리는 병렬 진행하지 않는다 |
| Qdrant 컬렉션 | 같은 컬렉션을 쓰는 feature끼리 회피 |
| `db/migration/V0xx__` 번호 | 브랜치 간 번호 선점 충돌 — 착수 시 번호를 먼저 확정한다 |
| 포트 8000 / 5173 | worktree별 `.env`에서 분리 |

> 테스트는 병렬 실행해도 안전하다 — 이 저장소의 테스트는 mock 또는
> `sqlite+aiosqlite` 임시파일을 쓰고 실 MySQL/Qdrant에 붙지 않는다.

---

## 1. Branch 생성

### 네이밍 규칙

```
<type>/<short-description>
```

| type | 사용 상황 |
|------|-----------|
| `feature/` | 새 기능 |
| `fix/` | 버그 수정 |
| `chore/` | 설정, 의존성, 빌드 |
| `refactor/` | 리팩토링 |
| `docs/` | 문서 |
| `test/` | 테스트 추가/수정 |

**예시**
```
feature/user-auth
fix/login-redirect-loop
chore/update-dependencies
```

### 명령어

**모드 A (worktree, 기본)** — 브랜치 생성이 worktree 생성에 포함된다:

```bash
git worktree add ../wt/<name> -b feature/xxx <BASE>
```

**모드 C (단일 폴더)** — 다른 세션이 돌고 있지 않을 때만:

```bash
git switch <BASE>            # <BASE>는 감지한 값 (이 저장소는 master)
git pull origin <BASE>       # 최신화 필수
git switch -c feature/xxx
```

> ⚠️ 항상 최신 `<BASE>`에서 브랜치를 따야 한다. 작업 전 반드시 pull.
> ⚠️ 모드 C를 쓰기 전에 `git worktree list`로 다른 작업 공간이 열려 있는지 확인한다.

---

## 2. 코드 작업

- Claude Code가 파일을 수정하는 단계
- 작업 전 `git status`로 현재 상태 확인
- 작업 단위가 크면 **논리적 단위로 커밋을 쪼갠다** (하나의 커밋 = 하나의 의도)

---

## 3. Commit

### Conventional Commits 형식

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**type 목록**

| type | 의미 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `chore` | 빌드/설정/패키지 |
| `refactor` | 동작 변경 없는 코드 개선 |
| `docs` | 문서 |
| `test` | 테스트 |
| `style` | 포맷, 세미콜론 등 (로직 무관) |
| `perf` | 성능 개선 |
| `ci` | CI/CD 설정 |

**subject 규칙**
- 50자 이내
- 현재형 동사로 시작 (add, fix, update, remove...)
- 끝에 마침표 없음
- 한국어 사용 가능 (팀 컨벤션 따름)

**예시**
```
feat(auth): add JWT refresh token logic
fix(api): handle null response from user endpoint
chore: update eslint to v9
refactor(db): extract query builder into separate module
```

### 명령어

```bash
git status                          # 변경 파일 확인
git diff                            # 변경 내용 확인
git add .                           # 전체 stage (또는 git add <file>)
git commit -m "feat(scope): 내용"
```

> 커밋 전 `git diff --staged`로 staged 내용을 한 번 더 확인하는 습관.

---

## 4. Push

```bash
git push -u origin <branch-name>
```

- `-u` 옵션으로 upstream 설정 (이후 `git push`만으로 가능)
- force push는 절대 `<BASE>`에 하지 않는다
- 같은 브랜치 재push 시 `git push` (이미 upstream 설정된 경우)

---

## 5. PR 생성 (gh CLI)

### 기본 명령어

```bash
gh pr create \
  --title "<type>(<scope>): <제목>" \
  --body "<PR 본문>" \
  --base <BASE>
```

> `--base`를 생략하면 GitHub 기본 브랜치가 쓰이지만, 명시하는 편이 안전하다.
> **`main`으로 하드코딩하지 않는다** — 이 저장소는 `master`다.

### PR 제목

커밋 메시지와 동일한 Conventional Commits 형식 사용:
```
feat(auth): JWT refresh token 구현
fix(api): 사용자 엔드포인트 null 응답 처리
```

### PR 본문 템플릿

```markdown
## 작업 내용
- 변경한 내용을 bullet point로 간결하게

## 변경 이유
- 왜 이 변경이 필요한지

## 테스트
- [ ] 로컬 테스트 완료
- [ ] 관련 테스트 추가/수정

## 스크린샷 (UI 변경 시)
```

### 옵션들

```bash
# reviewer 지정
gh pr create --reviewer <github-username>

# draft PR (아직 리뷰 준비 안 됐을 때)
gh pr create --draft

# label 추가
gh pr create --label "feature"

# 여러 옵션 조합
gh pr create \
  --title "feat(auth): JWT refresh token 구현" \
  --body "..." \
  --base <BASE> \
  --reviewer teammate1,teammate2 \
  --label "feature"
```

---

## 6. Conflict 해소

### 언제 발생하나?

- `git pull origin <BASE>` 시 — 내 브랜치 작업 중 `<BASE>`가 먼저 변경된 경우
- `git merge` / `git rebase` 시
- **병렬 작업 시 특히 자주 발생한다** — 다른 worktree의 PR이 먼저 머지되면
  내 브랜치는 그만큼 뒤처진다. 장기 feature일수록 주기적으로 `<BASE>`를 당겨온다.

### 전략 선택

| 상황 | 권장 전략 |
|------|-----------|
| 커밋이 1~2개, 히스토리 깔끔하게 유지하고 싶을 때 | **rebase** |
| 커밋이 많거나 팀이 merge를 선호할 때 | **merge** |
| 잘 모르겠을 때 기본값 | **merge** (안전) |

---

### 방법 A — merge (기본, 안전)

```bash
git fetch origin                # 원격 최신화 (브랜치 전환 없음)
git merge origin/<BASE>         # <BASE>를 내 브랜치에 병합
```

> ⚠️ **worktree에서는 `git checkout <BASE>`가 실패한다.** `<BASE>`는 메인 폴더가
> 이미 체크아웃하고 있어서 같은 브랜치를 두 워킹트리가 동시에 가질 수 없다.
> 위처럼 `fetch` + `origin/<BASE>` 병합을 쓰면 브랜치를 전환할 필요가 없고,
> 단일 폴더 모드에서도 그대로 동작한다.

conflict 파일이 생기면:

```bash
git status                   # conflict 난 파일 목록 확인
# 파일 열어서 직접 수정 (아래 마커 제거)
```

conflict 마커 형태:
```
<<<<<<< HEAD          ← 내 브랜치 내용
내가 작성한 코드
=======
<BASE>에서 온 코드
>>>>>>> origin/<BASE>
```

마커를 지우고 원하는 최종 코드만 남긴 뒤:

```bash
git add <conflict-resolved-file>
git commit                   # merge commit 자동 생성
```

---

### 방법 B — rebase (히스토리 깔끔)

```bash
git fetch origin
git rebase origin/<BASE>     # 이미 내 브랜치에 있는 상태에서 실행
```

conflict 발생 시:

```bash
# 파일 수정 후
git add <file>
git rebase --continue        # 다음 커밋으로 진행
# (conflict가 여러 커밋에 걸쳐 있으면 반복)
```

중단하고 싶으면:
```bash
git rebase --abort           # rebase 전 상태로 완전 복구
```

> ⚠️ rebase 후 push는 `git push --force-with-lease` 사용.  
> `--force`는 남의 커밋을 덮을 수 있으니 금지. `--force-with-lease`는 원격에 새 커밋이 있으면 push를 막아줌.

---

### ⚠️ Conflict 해소는 반드시 사람이 직접 한다

Conflict는 **비즈니스 로직의 충돌**이다. AI가 임의로 선택하면 안 된다.

Claude가 해야 할 일:
1. conflict 난 파일 목록을 보여준다
   ```bash
   git status
   ```
2. 각 파일의 conflict 마커를 보여준다
   ```bash
   git diff
   ```
3. **사용자에게 판단을 넘긴다**
   ```
   ⚠️ Conflict가 발생했습니다. 직접 확인이 필요합니다.

   충돌 파일:
   - src/auth/user.ts
   - src/config/roles.ts

   각 파일을 열어서 <<<<<<< / ======= / >>>>>>> 마커를 찾아
   어떤 코드를 남길지 직접 결정해주세요.
   완료되면 "해결했어" 라고 알려주세요.
   ```
4. 사용자가 완료 신호를 보내면 이어서 진행
   ```bash
   git add <resolved-files>
   git commit  # 또는 git rebase --continue
   ```

Claude가 하면 안 되는 것:
- conflict 마커를 보고 어느 쪽 코드를 남길지 스스로 결정
- "내 코드가 맞을 것 같으니 HEAD를 선택"하는 임의 판단

취소가 필요하면:
```bash
git merge --abort    # merge 전 상태로 복구
git rebase --abort   # rebase 전 상태로 복구
```

---

## 체크리스트 (PR 전 확인)

```
□ <BASE>를 감지했는가? (하드코딩된 main을 쓰지 않았는가)
□ 최신 <BASE>에서 브랜치를 생성했는가?
□ 전용 worktree(또는 슬롯)에서 작업했는가? 메인 폴더를 오염시키지 않았는가?
□ 브랜치명이 컨벤션에 맞는가? (feature/xxx)
□ 커밋 메시지가 Conventional Commits 형식인가?
□ 불필요한 파일이 commit에 포함되지 않았는가? (.env, node_modules, .bkit/runtime 등)
□ db/migration 번호가 다른 브랜치와 겹치지 않는가?
□ PR 제목과 본문이 충분히 설명적인가?
□ --base 가 <BASE>로 지정되었는가?
```

---

## 자주 쓰는 보조 명령어

```bash
# 현재 브랜치 확인
git branch

# 열려 있는 작업 공간 확인 (= 진행 중인 feature 목록)
git worktree list

# 기본 브랜치 감지
git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'

# 커밋 히스토리 확인
git log --oneline -10

# PR 목록 확인
gh pr list

# 내 PR 상태 확인
gh pr status

# PR 웹에서 열기
gh pr view --web
```

---

## PDCA 연동

이 저장소는 PDCA 사이클로 작업한다. **PDCA phase와 git 단계를 1:1로 맞춘다.**

아래 표의 `<P>`는 **작업 대상 프로젝트의 docs 루트**다. PDCA 문서 트리가 3개이므로
어느 것인지 먼저 정한다:

| 작업 범위 | `<P>` |
|-----------|-------|
| 백엔드 (기본, 문서 38건) | `idt/docs` |
| 프론트엔드 | `idt_front/docs` |
| 두 프로젝트에 걸친 cross-project 기능 | `docs` (루트) |

| PDCA phase | git 액션 | 커밋 대상 |
|------------|----------|-----------|
| `pm` / `plan` | `git worktree add ../wt/<f> -b feature/<f> <BASE>` | `<P>/01-plan/features/<f>.plan.md` |
| `design` | (그대로) | `<P>/02-design/features/<f>.design.md` |
| `do` | 논리 단위로 commit (`feat(scope): …`) | `src/`, `tests/` |
| `check` / `act` | 개선분 추가 commit (`fix:` / `refactor:`) | 구현 + `<P>/03-analysis/` |
| `qa` | `git push -u origin feature/<f>` | — |
| `report` | `gh pr create --base <BASE>` → 리뷰 → 머지 | `<P>/04-report/` |
| `archive` | junction 제거 → `git worktree remove` → `git branch -d` | — |

**병렬 PDCA 규칙**
- feature 하나 = worktree 하나 = 브랜치 하나 = CC 세션 하나.
- `.bkit/runtime`, `.bkit/state`는 worktree마다 독립이어야 한다.
  git에 추적된 상태로 남아 있으면 머지할 때마다 충돌하므로, 발견하면
  커밋에 포함시키지 말고 사용자에게 보고한다.
- 공유 파일은 브랜치에서 각자 고치면 충돌한다. 머지 후 `<BASE>`에서 일괄 갱신한다:
  - `idt/docs/task-registry.md`
  - `docs/wiki/_INDEX.md` (루트)
  - `docs/SOURCE-OF-TRUTH.md` (루트)

> ⚠️ **bkit의 `/pdca` 는 이 규칙을 자동으로 실행하지 않는다.**
> bkit 스킬에는 git/worktree 개념이 없어서(2.1.35 기준 언급 0건),
> worktree 생성·제거는 이 스킬을 통해 **사람이나 Claude가 명시적으로** 해야 한다.
> `/pdca plan` 을 시작할 때 전용 작업 공간이 없으면 `/feature <f>` 를 먼저 제안한다.

---

## 주의사항

- `<BASE>` 브랜치에 직접 commit하지 않는다
- `.env`, `*.log`, `node_modules`, `.bkit/runtime` 등 민감/불필요 파일이
  stage되지 않도록 `.gitignore` 확인
- 커밋 하나에 너무 많은 변경을 담지 않는다 (리뷰어 배려)
- PR 생성 후 CI가 돌면 결과를 확인한다: `gh pr checks`
- **다른 세션이 사용 중인 워킹트리에서 브랜치를 전환하지 않는다** — 미커밋 작업이 유실된다