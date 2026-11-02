# /ideas

프로젝트의 SoT 문서(유저 시나리오·성장 비전 로드맵·SOURCE-OF-TRUTH·위키·PDCA 아카이브)와 코드를 대조해
**"약속했지만 아직 없는 것"** 을 찾아 다음 기능 후보를 `docs/proposals/<YYYY-MM-DD>.md` 한 파일로 만든다.
추천마다 페르소나·시나리오·로드맵 Phase·근거 경로·왜 아직 없는지를 단다. 일반론적 위시리스트는 내지 않는다.

실제 작업은 `feature-scout` 서브에이전트(`.claude/agents/feature-scout.md`)가 수행한다.
이 명령은 후보 목록만 만든다. 착수는 사용자가 고른 뒤 `/pdca plan <slug>`로 시작한다.

## 사용법
```
/ideas [--focus <P2|S1|Phase 2|backend|frontend|자유 문장>] [--count N] [--note "부가 지시"]
```

예시:
```
/ideas
/ideas --focus P2
/ideas --focus "Phase 2" --count 5
/ideas --focus frontend --note "관리자 화면 쪽은 제외"
```

## 실행 순서

### 1. 인자 파싱

- `--focus` 기본 없음(전체). 페르소나(P1~P4), 시나리오(S1~S5), 로드맵 Phase, 영역(backend/frontend), 자유 문장 모두 허용. 따옴표는 벗긴다.
- `--count` 기본 8. 3~15 밖이면 경계값으로 보정한다.
- `--note` 기본 없음.
- 오늘 날짜(`YYYY-MM-DD`)를 확정한다. `docs/proposals/<date>.md`가 이미 있으면 덮어쓴다고 사용자에게 한 줄 알린다.

### 2. 에이전트 스폰

`Agent` 도구로 `feature-scout`를 스폰한다. **직접 후보를 쓰지 않는다.**
프롬프트에 아래를 그대로 담는다(에이전트는 이 대화를 볼 수 없다):

```
오늘 날짜: <date>
초점(focus): <focus 또는 "없음(전체)">
개수(count): <count>
부가 지시: <note 또는 "없음">
이번 세션에서 알게 된 관련 사실: <있으면 요약, 없으면 "없음">
```

SoT 문서·아카이브·코드를 전부 읽으므로 시간이 걸린다. 끝날 때까지 기다린다.

### 3. 결과 전달

에이전트 보고(산출물 경로, 로드맵 판정, 후보/기각/진행 중 수, 상위 3개, 확인 필요)를 사용자에게 그대로 전달하고 아래를 안내한다.

- 후보 목록: `docs/proposals/<date>.md`
- 착수: 카드의 slug로 `/pdca plan <slug>`
- §6 "확인 필요·SOT 어긋남"에 SOURCE-OF-TRUTH와 코드의 불일치가 있으면, CLAUDE.md §6 규칙대로 **코드가 진실**이며 문서는 사용자가 고칠지 정한다

### 4. 후속 (사용자가 요청할 때만)

- "n번 더 자세히" → 해당 카드의 근거 경로를 직접 읽고 대화로 설명 (에이전트 재스폰 불필요)
- "n번 착수" → `/pdca plan <slug>` 실행
- "다시 뽑아줘" / 초점 바꿔서 → 에이전트 재스폰 (같은 날짜면 덮어씀)

## 하지 않는 것

- 코드·테스트 수정, `/pdca plan` 문서 자동 생성, `.bkit/` 상태 변경
- 위키·CLAUDE.md·SOURCE-OF-TRUTH 수정 (어긋남은 보고만)
- 커밋·푸시 (원하면 `/commit`)
