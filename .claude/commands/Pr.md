# /pr

현재 브랜치를 push하고 GitHub PR을 생성한다.

## 사용법
```
/pr
/pr --draft
/pr --reviewer teammate1,teammate2
```

## 실행 순서

0. 기본 브랜치(`<BASE>`) 감지
   ```bash
   git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'
   ```
   - 결과를 이후 모든 명령의 `<BASE>`로 사용한다. **`main`으로 하드코딩하지 않는다**
     (이 저장소는 `master`다).
   - 실패 시 → `git remote set-head origin -a` 로 복구 후 재실행.

1. 현재 상태 확인
   ```bash
   git status
   git fetch origin <BASE>
   git log --oneline origin/<BASE>..HEAD   # <BASE> 대비 내 커밋 목록
   ```
   - uncommitted 변경사항이 있으면 먼저 /commit 하도록 안내
   - 커밋 목록이 비어 있으면 → PR을 만들 게 없다는 뜻. 중단하고 사용자에게 알린다
     (브랜치를 잘못 잡았거나 `<BASE>` 감지가 틀린 경우가 대부분)

2. Push
   ```bash
   git push -u origin <current-branch>
   ```
   - 이미 upstream 설정된 경우: `git push`
   - rebase 후라면: `git push --force-with-lease`

3. PR 제목 생성
   - 마지막 커밋 메시지 또는 커밋 목록을 기반으로 자동 생성
   - Conventional Commits 형식 유지

4. PR 본문 자동 생성
   ```markdown
   ## 작업 내용
   - (커밋 목록 기반으로 자동 작성)

   ## 변경 이유
   - (사용자에게 입력 요청 또는 컨텍스트에서 추론)

   ## 테스트
   - [ ] 로컬 테스트 완료
   - [ ] 관련 테스트 추가/수정
   ```

5. PR 생성
   ```bash
   gh pr create \
     --title "<title>" \
     --body "<body>" \
     --base <BASE>
   ```
   - `--draft` 옵션 전달 시 draft PR로 생성
   - `--reviewer` 옵션 전달 시 reviewer 지정

6. 완료 메시지
   ```
   ✅ PR 생성 완료!
   URL: https://github.com/...
   ```
   - `gh pr view --web` 으로 브라우저에서 열기 제안
   - worktree에서 작업했다면 머지 후 정리 방법을 함께 안내:
     ```
     머지되면 정리하세요:
       git worktree remove ../wt/<name>
       git branch -d <branch>
     ```