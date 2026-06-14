import os
import logging
from typing import Optional


logger = logging.getLogger(__name__)

_PROJECT_NAME_MAX = 128

def langsmith(project_name=None, set_enable=True):

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


def make_agent_run_tracer(
    agent_name: Optional[str],
    tags: Optional[list[str]] = None,
):
    """에이전트별 프로젝트로 보내는 per-run LangChainTracer 생성 (best-effort).

    Design §2: graph_config["callbacks"]에 주입해 전역 os.environ 변경 없이
    run별 프로젝트를 지정한다. langchain_core는 명시적 LangChainTracer가 있으면
    전역 auto-tracer를 추가하지 않으므로 중복/경합이 없다.

    - API 키 없으면 None (추적 비활성, 본 흐름 영향 없음).
    """
    key = os.environ.get("LANGCHAIN_API_KEY", "") or os.environ.get(
        "LANGSMITH_API_KEY", ""
    )
    if not key.strip():
        return None
    try:
        from langchain_core.tracers import LangChainTracer

        return LangChainTracer(
            project_name=normalize_agent_project_name(agent_name),
            tags=tags,
        )
    except Exception as e:  # pragma: no cover - 방어적 best-effort
        logger.warning("make_agent_run_tracer failed: %s", e)
        return None