# /pr

현재 브랜치를 push하고 GitHub PR을 생성한다.

## 사용법
```
/pr
/pr --draft
/pr --reviewer teammate1,teammate2
```

## 실행 순서

1. 현재 상태 확인
   ```bash
   git status
   git log --oneline main..HEAD   # main 대비 내 커밋 목록
   ```
   - uncommitted 변경사항이 있으면 먼저 /commit 하도록 안내

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
     --base main
   ```
   - `--draft` 옵션 전달 시 draft PR로 생성
   - `--reviewer` 옵션 전달 시 reviewer 지정

6. 완료 메시지
   ```
   ✅ PR 생성 완료!
   URL: https://github.com/...
   ```
   - `gh pr view --web` 으로 브라우저에서 열기 제안