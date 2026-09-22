"""테스트 전역 픽스처.

pipeline-langsmith-tracing §4-2 — LangSmith 자격증명 격리.

`src/api/main.py:20` 이 import 시점에 `load_dotenv()` 를 호출하므로, api 테스트가
하나라도 먼저 돌면 실제 `.env` 의 `LANGCHAIN_API_KEY` 가 `os.environ` 에 올라온다.
그 상태에서는

  · 추적 코드가 **실제 LangSmith 로 run 을 POST** 한다 (테스트가 네트워크를 탄다)
  · tracer 가 생겨 `config`/`callbacks` 가 붙으므로, 그것을 받지 않는 테스트
    대역(`_fake_astream_events(input_dict, version=None)`)이 TypeError 로 깨진다

**스코프가 session 인 이유** (Check 단계 회귀로 학습):
처음엔 함수 스코프 autouse + `monkeypatch` 로 썼는데, 루트 conftest 의 함수
스코프 autouse 가 **모든** 테스트의 픽스처 그래프에 끼어들면서 DB 엔진 픽스처와
이벤트 루프 생명주기가 어긋나 `RuntimeError: Event loop is closed` 가 91건
발생했다 (동일 조건 대조: conftest 있음 91 errors / 없음 0 errors).

키 격리는 프로세스 전역 1회면 충분하고, 키를 **쓰는** 테스트는 스스로
`monkeypatch.setenv` 하므로(함수 스코프라 이 픽스처보다 나중에 적용되고 자동
복원된다) 영향을 받지 않는다.
"""
import pytest

_LANGSMITH_ENV = (
    "LANGCHAIN_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
)


@pytest.fixture(scope="session", autouse=True)
def isolate_langsmith_env() -> None:
    """테스트는 실제 LangSmith 자격증명을 물려받지 않는다."""
    mp = pytest.MonkeyPatch()
    for name in _LANGSMITH_ENV:
        mp.delenv(name, raising=False)
    yield
    mp.undo()
