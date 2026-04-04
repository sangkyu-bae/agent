# /feature

새 feature 브랜치를 생성한다.

## 사용법
```
/feature <description>
```

예시:
```
/feature user-auth
/feature fix/login-redirect
```

## 실행 순서

1. 현재 브랜치와 working tree 상태 확인
   ```bash
   git status
   git branch
   ```

2. 미완료 작업이 있으면 사용자에게 확인 (stash 또는 commit 먼저 할지)

3. main(또는 develop) 브랜치로 이동 후 최신화
   ```bash
   git checkout main
   git pull origin main
   ```
   - conflict 발생 시 → **작업 중단, 사용자에게 알리고 대기**
     ```
     ⚠️ git pull 중 conflict가 발생했습니다. 직접 해결이 필요합니다.
     SKILL.md의 "Conflict 해소" 섹션을 참고하세요.
     해결 완료 후 "해결했어"라고 알려주시면 이어서 진행합니다.
     ```

4. 브랜치 중복 확인
   ```bash
   git branch --list feature/<description>
   ```
   - **브랜치가 이미 존재하면** → 작업 중단 후 사용자에게 안내:
     ```
     ⚠️ feature/<description> 브랜치가 이미 존재합니다.
     이전 작업이 아직 머지되지 않았을 수 있어요.

     A) 기존 브랜치로 이동해서 이어서 작업
     B) 다른 이름으로 새 브랜치 생성 (예: feature/<description>-2)
     C) 취소

     어떻게 할까요?
     ```
   - **A 선택 시**: `git checkout feature/<description>` 후 현재 상태 요약 출력
     ```bash
     git log --oneline main..HEAD   # 이전 커밋 목록 확인
     git status                     # 미완료 작업 확인
     ```
   - **B 선택 시**: 새 이름 입력받아 브랜치 생성
   - **C 선택 시**: 종료

5. 브랜치 생성 (중복 없는 경우)
   - `<description>`에 type prefix가 없으면 `feature/`를 자동으로 붙인다
   - `fix/login`처럼 type이 명시된 경우 그대로 사용
   ```bash
   git checkout -b feature/<description>
   ```

5. 완료 메시지 출력
   ```
   ✅ 브랜치 생성 완료: feature/<description>
   이제 작업을 시작하세요. 완료되면 /commit 으로 커밋하세요.
   ```