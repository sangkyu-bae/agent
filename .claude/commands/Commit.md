# /commit

변경사항을 Conventional Commits 형식으로 커밋한다.

## 사용법
```
/commit
/commit "feat(auth): add JWT refresh token"
```

- 메시지를 주면 그대로 사용
- 메시지를 안 주면 변경사항을 분석해서 자동 생성

## 실행 순서

1. 변경사항 확인
   ```bash
   git status
   git diff
   ```

2. 커밋 메시지 결정
   - 인자로 메시지가 주어진 경우 → 그대로 사용 (형식 검증만)
   - 메시지가 없는 경우 → diff를 분석해서 Conventional Commits 형식으로 자동 생성
     - type: feat / fix / chore / refactor / docs / test / style / perf / ci
     - subject: 50자 이내, 현재형 동사, 마침표 없음
   - 생성한 메시지를 사용자에게 보여주고 확인 받기

3. Stage & Commit
   ```bash
   git add .
   git diff --staged   # staged 내용 최종 확인
   git commit -m "<message>"
   ```

4. 불필요한 파일 경고
   - `.env`, `node_modules/`, `*.log`, `dist/`, `.DS_Store` 등이 staged되면 경고 후 중단

5. 완료 메시지
   ```
   ✅ 커밋 완료: <message>
   push하려면 /pr 또는 git push를 실행하세요.
   ```