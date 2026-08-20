"""prompt-composer Design §8.1 L3 — 실 LLM 왕복 1건 (Plan R2 완화책).

**CI 제외.** 실제 LLM을 호출하므로 `-m llm`으로 명시 실행한다:

    pytest -m llm tests/infrastructure/prompt_composer/test_real_llm.py -s

이 테스트가 존재하는 이유(Plan §5 R2): 이 모듈은 **배선 없이 출하**되므로
`with_structured_output(_PromptDraft)`가 실제 모델에서 파싱되는지 확인할 다른
경로가 없다. 스키마가 깨져 있어도 어댑터가 degraded로 흡수해버리기 때문에
대역 테스트로는 절대 드러나지 않는다 — 그래서 `degraded=False`를 단언한다.
"""
import os

import pytest
from dotenv import load_dotenv
from src.config import settings
from src.domain.prompt_composer.policies import PromptAssemblyPolicy
from src.domain.prompt_composer.schemas import ToolMeta
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.prompt_composer.adapter import LLMPromptGeneratorAdapter

pytestmark = pytest.mark.llm

_METAS = (
    ToolMeta(
        tool_id="internal:excel_export",
        name="엑셀 내보내기",
        description="정리된 표 데이터를 엑셀 파일로 저장한다",
        source="internal",
    ),
    ToolMeta(
        tool_id="internal:doc_search",
        name="문서 검색",
        description="사내 문서에서 질의에 해당하는 원문을 찾는다",
        source="internal",
    ),
)
_REQUEST = "사내 규정 문서를 찾아 근거와 함께 답하고 결과를 엑셀로 내보내는 봇"

# prompt-depth FR-19 — 신규 2축이 프롬프트에 도달해 context/principles 의 근거가
# 되는지를 실 모델에서 확인한다. 대역으로는 "블록이 실렸다"까지만 알 수 있다.
_INTENT = {
    "label": "agent_create",
    "degraded": False,
    "reason": "에이전트 생성 요청",
    "filled_slots": {
        "target_users": "여신 심사 실무자",
        "tone": "격식체",
        "constraints": "규정 원문에 없는 내용을 지어내지 않는다",
        "decision_priority": "정확성 우선",
    },
}


def _ensure_api_key() -> bool:
    """프로덕션과 동일하게 .env를 os.environ에 로드한다.

    pydantic-settings는 `.env`를 읽어도 os.environ에 넣지 않는다. 실행 경로에서는
    `api/main.py`의 `load_dotenv()`가 이 역할을 한다.
    """
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") and getattr(settings, "openai_api_key", ""):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    return bool(os.getenv("OPENAI_API_KEY"))


async def test_real_llm_generates_structured_sections():
    """실 모델이 `_PromptDraft` 스키마로 파싱되고 후보 밖 도구를 만들지 않는다."""
    if not _ensure_api_key():
        pytest.skip("OPENAI_API_KEY 없음 — 실 LLM 테스트 건너뜀")

    adapter = LLMPromptGeneratorAdapter(
        logger=StructuredLogger(name="prompt-composer-l3", level=40)
    )
    sections, degraded, reason, elapsed = await adapter.generate(
        _REQUEST, _METAS, _INTENT, [], "l3-real-llm"
    )

    # degraded=True면 스키마 파싱이 깨진 것이다 — 폴백에 가려지지 않게 여기서 잡는다.
    # prompt-depth R-01/SC-6: 7섹션 확장 후 strict 400 이 나면 여기서만 드러난다.
    assert degraded is False, f"실 LLM 생성 실패: reason={reason}"
    assert sections.purpose.strip()
    assert sections.roles, "역할이 하나도 생성되지 않았다 (Q1 — 자유 생성)"

    known = {meta.tool_id for meta in _METAS}
    assert {g.tool_id for g in sections.tool_guides} <= known, "후보 밖 도구 환각"
    assert elapsed > 0

    _report(sections, elapsed)


def _report(sections, elapsed: int) -> None:
    """prompt-depth §8.3 — 7섹션 충족률·지연·길이 실측 보고.

    O-1(타임아웃 상향) / O-2(지침 조정) / R-03(토큰 비용) 판단의 유일한 근거다.
    단언은 §8.3-2 의 6섹션에만 건다 — `context` 는 요청에 제약이 없으면 LLM 이
    비우는 것이 정상이므로 실패로 칠 수 없다.
    """
    assembled = PromptAssemblyPolicy.assemble(sections)
    filled = {
        "purpose": bool(sections.purpose.strip()),
        "identity": bool(sections.identity.strip()),
        "context": sections.context is not None,
        "roles": bool(sections.roles),
        "tool_guides": bool(sections.tool_guides),
        "workflows": bool(sections.workflows),
        "style": bool(sections.style.strip()),
        "principles": bool(sections.principles),
    }
    # 콘솔 인코딩이 cp949 인 환경이 있다 — 보고 출력에 비ASCII 기호를 쓰지 않는다.
    print(f"\n[L3] elapsed={elapsed}ms assembled_chars={len(assembled)}")
    print(f"[L3] filled={sum(filled.values())}/8 {filled}")
    print(f"[L3] ---- assembled ----\n{assembled}\n[L3] --------------------")

    for name in ("purpose", "identity", "roles", "workflows", "style", "principles"):
        assert filled[name], f"'{name}' 섹션이 비었다 (Plan R-02 — 지침 조정 필요)"
