# Archive Index — 2026-08

| Feature | Phase | Match Rate | Archived At | Path |
|---------|-------|:----------:|-------------|------|
| eval-hub | completed | 98% | 2026-08-03 | [eval-hub/](eval-hub/) |
| fix-agent-planner-hitl | completed | 100% | 2026-08-06 | [fix-agent-planner-hitl/](fix-agent-planner-hitl/) |
| agent-create-entry | completed | 96% | 2026-08-13 | [agent-create-entry/](agent-create-entry/) |
| intent-analyzer | completed (Partial) | 100% | 2026-08-13 | [intent-analyzer/](intent-analyzer/) |
| tool-recommender | completed | 97.38% | 2026-08-14 | [tool-recommender/](tool-recommender/) |

---

## 이월 항목 (Carry-over)

> 아카이브 시점에 미완이었던 항목. 후속 사이클 진입 전 확인할 것.

| Feature | 이월 항목 | 성격 | 진입 조건 |
|---------|----------|------|-----------|
| **intent-analyzer** | **실 LLM 호출 검증 1회 (G1)** — Design §4.3 프롬프트가 위키 계약 2(목록 프레이밍 과차단, 커밋 08d37cab 실장애)를 실제로 이겨내는지 미실증. fake chain 테스트는 프롬프트 *조립*만 검증한다 | 환경 의존 (서버 기동 + `OPENAI_API_KEY`), 자동화 불가 | **배선 사이클(Design §11.4 shadow 1단계) 진입 전 필수 해소** |
| intent-analyzer | 배선 자체 — supervisor shadow 1단계 → 조언 주입 2단계 | 의도적 스코프 밖 (Plan D8) | G1 해소 후 |
| intent-analyzer | 전체 스위트 기존 실패 58건 (parser 21 / agent_builder_stream 9 / retriever 7 / general_chat 7 …) | 본 기능 무관 — 라이브러리 버전 드리프트 | 독립 사이클 |
| **tool-recommender** | **Recall 100%는 후보 13개 기준** — Design §8.5 목표 규모(40+)에서의 Recall·지연 미검증. 도구가 많아질수록 오추천이 는다는 것이 Plan의 최초 문제의식인데, 정작 그 규모를 실측하지 못했다 | 환경 의존 (Naver Search MCP 복구 대기) | MCP 서버 확보 후 골드셋 풀 확장 재측정 |
| tool-recommender | MCP 저시그널 설명 보강(§3.3 name 토큰화) 효과 미측정 — 수집된 실 MCP 도구 4건 모두 완전한 docstring, stub 0건 | Plan 전제("MCP 설명은 stub")가 보편적이지 않았음 | stub 설명을 가진 MCP 등록 시 |
| tool-recommender | 커스텀 에이전트(`workflow_compiler`) 미배선 — General Chat 경로만 적용 | 의도적 스코프 밖 (module-4 한정) | 별도 사이클 |
| tool-recommender | `TOOL_SELECTOR_ENABLED=true`는 **로컬 `idt/.env`에만** 존재 (gitignore). 다른 환경은 코드 기본값 `False`로 꺼져 있다 | 배포 절차 | 스테이징/운영 적용 시 환경변수 주입 필요 |
