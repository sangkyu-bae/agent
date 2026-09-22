import os
import logging
from contextlib import contextmanager, nullcontext
from typing import Iterator, Optional

from langchain_core.tracers.context import tracing_v2_enabled


logger = logging.getLogger(__name__)

_PROJECT_NAME_MAX = 128


def _api_key() -> str:
    """LangSmith API 키 (LANGCHAIN_/LANGSMITH_ 둘 다 허용). 없으면 빈 문자열.

    Design Ref: pipeline-langsmith-tracing §3-1 — `_make_project_tracer` 와
    `pipeline_tracing` 이 같은 판별 규칙을 써야 한 쪽만 추적되는 일이 없다.
    """
    return (
        os.environ.get("LANGCHAIN_API_KEY", "")
        or os.environ.get("LANGSMITH_API_KEY", "")
    ).strip()


def _tracing_enabled() -> bool:
    """추적 가능 여부 = API 키 보유 여부 (Design D2)."""
    return bool(_api_key())

def langsmith(project_name=None, set_enable=True):
    """**Deprecated** — `os.environ` 을 영구 변경한다 (pipeline-langsmith-tracing §1-3).

    되돌리는 코드가 없어 한 번 호출되면 이후 **모든** LangChain 호출이 마지막
    `LANGSMITH_PROJECT` 로 흘러간다. 실측상 이 방식은 실행 중에도 run tree 를
    남기지 않는다(Design §4-2 조사).

    대체:
      · 스트리밍/그래프 config 가 있는 경로 → `make_*_tracer()` 를 callbacks 에
      · 단일 await 경로 → `scoped_tracing(project_name)`
    """
    if set_enable:
        langchain_key = os.environ.get("LANGCHAIN_API_KEY", "")
        langsmith_key = os.environ.get("LANGSMITH_API_KEY", "")

        # 더 긴 API 키 선택
        if len(langchain_key.strip()) >= len(langsmith_key.strip()):
            result = langchain_key
        else:
            result = langsmith_key

        if result.strip() == "":
            logger.info(
                "LangChain/LangSmith API Key가 설정되지 않았습니다."
            )
            return

        os.environ["LANGSMITH_ENDPOINT"] = (
            "https://api.smith.langchain.com"  # LangSmith API 엔드포인트
        )
        os.environ["LANGSMITH_TRACING"] = "true"  # true: 활성화
        os.environ["LANGSMITH_PROJECT"] = project_name  # 프로젝트명
        logger.info(f"LangSmith 추적을 시작합니다.\n[프로젝트명]\n{project_name}")
    else:
        os.environ["LANGSMITH_TRACING"] = "false"  # false: 비활성화
        logger.info("LangSmith 추적을 하지 않습니다.")


def env_variable(key, value):
    os.environ[key] = value


def normalize_agent_project_name(agent_name: Optional[str]) -> str:
    """에이전트명 → LangSmith 프로젝트명.

    agent-run-langsmith-per-agent-project Design §3.1:
    공백 정규화·길이 제한, 빈 값이면 'agent-run' fallback.
    """
    base = " ".join((agent_name or "").split())
    if not base:
        return "agent-run"
    return f"agent-{base}"[:_PROJECT_NAME_MAX]


COMPOSER_PROJECT_NAME = "agent-composer"


def _make_project_tracer(project_name: str, tags: Optional[list[str]] = None):
    """지정 프로젝트로 보내는 per-run LangChainTracer 생성 (best-effort).

    graph_config["callbacks"]에 주입해 전역 os.environ 변경 없이 run별
    프로젝트를 지정한다. langchain_core는 명시적 LangChainTracer가 있으면
    전역 auto-tracer를 추가하지 않으므로 중복/경합이 없다.

    - API 키 없으면 None (추적 비활성, 본 흐름 영향 없음).
    """
    if not _tracing_enabled():
        return None
    try:
        from langchain_core.tracers import LangChainTracer

        return LangChainTracer(project_name=project_name, tags=tags)
    except Exception as e:  # pragma: no cover - 방어적 best-effort
        logger.warning("make tracer failed (project=%s): %s", project_name, e)
        return None


def make_agent_run_tracer(
    agent_name: Optional[str],
    tags: Optional[list[str]] = None,
):
    """에이전트별 프로젝트로 보내는 per-run tracer (Design §2)."""
    return _make_project_tracer(normalize_agent_project_name(agent_name), tags)


def make_composer_tracer(tags: Optional[list[str]] = None):
    """Agent Composer 추적용 per-run tracer — 고정 프로젝트 'agent-composer'.

    nl-agent-composer 추적: 어떤 요청으로 어떤 에이전트 초안이 조합됐는지
    LangSmith에서 run_name/metadata로 추적한다.
    """
    return _make_project_tracer(COMPOSER_PROJECT_NAME, tags)


DOCUMENT_EXTRACTOR_PROJECT_NAME = "document-extractor"

DOCUMENT_GENERATOR_PROJECT_NAME = "document-generator"

# pipeline-langsmith-tracing FR-06 — 전역 `langsmith()` 가 쓰던 프로젝트명을
# 그대로 승계한다. 이름이 바뀌면 기존 대시보드·저장된 필터가 끊긴다.
GENERAL_CHAT_PROJECT_NAME = "general-chat"

EXCEL_ANALYSIS_PROJECT_NAME = "excel-analysis-agent"


def make_general_chat_tracer(tags: Optional[list[str]] = None):
    """일반 채팅 추적용 per-run tracer — 고정 프로젝트 'general-chat'.

    Design Ref: pipeline-langsmith-tracing §4-2(편차) — `stream()` 은 async
    generator 라 그래프 호출(`astream_events`)이 본질적으로 `yield` 를 가로지른다.
    컨텍스트 매니저(`scoped_tracing`)를 쓰면 §7-2 를 위반하므로, 이미 존재하는
    `stream_kwargs["config"]["callbacks"]` 에 tracer 를 얹는 방식을 쓴다
    (`run_agent_use_case` 와 동형).
    """
    return _make_project_tracer(GENERAL_CHAT_PROJECT_NAME, tags)


def make_document_generator_tracer(tags: Optional[list[str]] = None):
    """문서생성기 추적용 per-run tracer — 고정 프로젝트 'document-generator'.

    문서 작성 LLM 호출을 run_name(generate:{유형명})으로 구분 추적한다 (D7).
    """
    return _make_project_tracer(DOCUMENT_GENERATOR_PROJECT_NAME, tags)


def make_document_extractor_tracer(tags: Optional[list[str]] = None):
    """문서추출기 추적용 per-run tracer — 고정 프로젝트 'document-extractor'.

    슬롯 추출/재추천(SlotExtractor)과 문서 합성(DocumentComposer)의 LLM 호출을
    run_name(slot-extract/slot-refine/compose:{템플릿명})으로 구분 추적한다.
    """
    return _make_project_tracer(DOCUMENT_EXTRACTOR_PROJECT_NAME, tags)


# ── 스코프 추적 (pipeline-langsmith-tracing §4) ──────────────────────────────

PIPELINE_PROJECT_NAME = "agent-create-pipeline"

PIPELINE_COMMON_TAG = "agent-create-pipeline"


@contextmanager
def scoped_tracing(
    project_name: str, tags: Optional[list[str]] = None
) -> Iterator[None]:
    """이 블록 안의 LangChain 호출만 지정 프로젝트로 추적한다.

    Design Ref: pipeline-langsmith-tracing §4-2 / D1.

    `langsmith()` 의 전역 `os.environ` 변경을 대체한다. contextvar 기반이라
    호출 스택 단위로 격리되므로, 여러 호출자가 공유하는 싱글턴 어댑터라도
    이 블록을 거친 호출에만 추적이 붙는다 (Design §2-2).

    **`yield` 를 가로질러 열지 말 것** (Design §7-2): async generator 본문에서
    이 컨텍스트가 `yield` 를 감싸면 contextvar 가 소비자 쪽으로 샌다.
    `await` 만 감싼다.

    - API 키가 없으면 아무것도 하지 않는다 (Design D2). `tracing_v2_enabled` 는
      키가 없어도 진입해 tracer 를 만들기 때문에 이 가드가 필요하다 (§7-1).
    - 추적 설정 실패가 본 흐름을 막지 않는다 (Plan NFR-01).
    """
    if not _tracing_enabled():
        yield
        return
    try:
        ctx = tracing_v2_enabled(project_name=project_name, tags=tags)
    except Exception as e:  # pragma: no cover - 방어적 best-effort
        logger.warning("scoped tracing setup failed (project=%s): %s", project_name, e)
        ctx = nullcontext()
    with ctx:
        yield


def _pipeline_tags(
    stage: str, request_id: str, round_: int, stop_after: Optional[str]
) -> list[str]:
    """단계 run 을 식별·묶기 위한 태그 (Design §3-2).

    `tracing_v2_enabled` 는 run_name/metadata 를 받지 않으므로 Plan 의
    run_name·metadata 요구를 태그로 대체한다 (Design §7-3).
    """
    return [
        PIPELINE_COMMON_TAG,
        f"stage:{stage}",
        f"request:{request_id}",
        f"round:{round_}",
        f"stop:{stop_after or 'none'}",
    ]


@contextmanager
def pipeline_tracing(
    stage: str,
    *,
    request_id: str,
    round_: int = 0,
    stop_after: Optional[str] = None,
) -> Iterator[None]:
    """에이전트 생성 파이프라인 한 단계의 추적 스코프.

    Design Ref: pipeline-langsmith-tracing §4-1 — `_stage()` 한 곳에서 열고 닫아
    5단계 전부를 덮는다. LLM 을 호출하지 않는 create/bind 단계는 컨텍스트만
    열렸다 닫히고 run 이 생기지 않는다(무해).

    Args:
        stage: `PipelineStage` 값 (StrEnum 이라 문자열로 그대로 쓴다)
        request_id: 한 요청의 단계들을 묶어 조회하기 위한 키 (Plan SC-02)
        round_: 되묻기 라운드
        stop_after: `PipelineStop` 값 또는 None(논스톱)
    """
    with scoped_tracing(
        PIPELINE_PROJECT_NAME,
        tags=_pipeline_tags(str(stage), request_id, round_, _as_str(stop_after)),
    ):
        yield


def _as_str(value: Optional[object]) -> Optional[str]:
    """StrEnum/None 을 태그용 문자열로. None 은 그대로 None."""
    return None if value is None else str(value)