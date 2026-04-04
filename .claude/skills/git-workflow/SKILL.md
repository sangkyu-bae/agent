---
name: git-workflow
description: >
  Claude Code에서 feature 작업 시 branch 생성 → 코드 작업 → commit → PR 생성까지
  전체 git 워크플로우를 일관되게 수행하는 skill. GitHub (gh CLI) 기반이며
  Conventional Commits 컨벤션을 따른다.
  다음 상황에서 반드시 이 skill을 사용하세요:
  - "feature 따줘", "브랜치 만들어줘", "PR 보내줘", "커밋해줘" 등 git 작업 요청
  - 기능 구현 후 "이제 올려줘", "push해줘" 라고 할 때
  - "작업 시작해줘", "이슈 작업 시작" 등 새 작업 착수 시
  - 코드 변경이 완료되어 리뷰 요청이 필요할 때
---

# Git Workflow Skill

GitHub + Conventional Commits 기반의 전체 git 워크플로우를 담당한다.

---

## 전체 플로우 요약

```
1. branch 생성      →  git checkout -b <branch>
2. 코드 작업        →  (Claude Code가 파일 수정)
3. 변경사항 확인    →  git status / git diff
4. stage & commit   →  git add . && git commit -m "..."
5. push             →  git push -u origin <branch>
6. PR 생성          →  gh pr create ...
```

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

```bash
git checkout main          # 또는 develop (프로젝트 기본 브랜치 확인)
git pull origin main       # 최신화 필수
git checkout -b feature/xxx
```

> ⚠️ 항상 최신 main(또는 develop)에서 브랜치를 따야 한다. 작업 전 반드시 pull.

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
- force push는 절대 main/develop에 하지 않는다
- 같은 브랜치 재push 시 `git push` (이미 upstream 설정된 경우)

---

## 5. PR 생성 (gh CLI)

### 기본 명령어

```bash
gh pr create \
  --title "<type>(<scope>): <제목>" \
  --body "<PR 본문>" \
  --base main
```

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
  --base main \
  --reviewer teammate1,teammate2 \
  --label "feature"
```

---

## 6. Conflict 해소

### 언제 발생하나?

- `git pull origin main` 시 — 내 브랜치 작업 중 main이 먼저 변경된 경우
- `git merge` / `git rebase` 시

### 전략 선택

| 상황 | 권장 전략 |
|------|-----------|
| 커밋이 1~2개, 히스토리 깔끔하게 유지하고 싶을 때 | **rebase** |
| 커밋이 많거나 팀이 merge를 선호할 때 | **merge** |
| 잘 모르겠을 때 기본값 | **merge** (안전) |

---

### 방법 A — merge (기본, 안전)

```bash
git checkout main
git pull origin main         # main 최신화
git checkout feature/xxx     # 내 브랜치로 돌아오기
git merge main               # main을 내 브랜치에 병합
```

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
main에서 온 코드
>>>>>>> main
```

마커를 지우고 원하는 최종 코드만 남긴 뒤:

```bash
git add <conflict-resolved-file>
git commit                   # merge commit 자동 생성
```

---

### 방법 B — rebase (히스토리 깔끔)

```bash
git checkout feature/xxx
git rebase origin/main
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
□ main(develop)에서 최신 pull 후 브랜치 생성했는가?
□ 브랜치명이 컨벤션에 맞는가? (feature/xxx)
□ 커밋 메시지가 Conventional Commits 형식인가?
□ 불필요한 파일이 commit에 포함되지 않았는가? (.env, node_modules 등)
□ PR 제목과 본문이 충분히 설명적인가?
□ base 브랜치가 올바른가? (main vs develop)
```

---

## 자주 쓰는 보조 명령어

```bash
# 현재 브랜치 확인
git branch

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

## 주의사항

- `main` / `develop` 브랜치에 직접 commit하지 않는다
- `.env`, `*.log`, `node_modules` 등 민감/불필요 파일이 stage되지 않도록 `.gitignore` 확인
- 커밋 하나에 너무 많은 변경을 담지 않는다 (리뷰어 배려)
- PR 생성 후 CI가 돌면 결과를 확인한다: `gh pr checks`