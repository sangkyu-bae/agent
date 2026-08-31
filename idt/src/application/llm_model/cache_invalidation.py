"""LLM 모델 변경 후 해석 캐시 무효화 공용 헬퍼.

Design Ref: admin-default-llm-routing §6.1 / AD-3 / U5.

관리자가 모델을 생성·수정·비활성화·가격변경하면 UseCase 가 이 함수를
의무 호출한다. 무효화 책임을 UseCase 안에 캡슐화해 router 나 테스트가
빼먹을 수 없게 한다 (update_llm_model_pricing_use_case 의 cost_calculator
선례와 동일 취지).
"""
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface


async def invalidate_llm_model_cache(
    provider: UtilityLLMProviderPort | None,
    logger: LoggerInterface,
    request_id: str,
    model_id: str | None = None,
) -> None:
    """보조 LLM 해석 캐시를 무효화한다.

    호출 시점에는 모델 변경이 **이미 DB에 반영된 뒤**다. 캐시 무효화 실패로
    예외를 올리면 "저장은 됐는데 실패로 응답되는" 상태가 되므로, 실패는
    warning 으로 남기고 삼킨다 — 남은 낡은 값은 TTL 로 수렴한다 (AD-4).

    Args:
        provider: 미주입(None)이면 아무것도 하지 않는다 (하위호환 — FR-9).
        logger: 실패 기록용.
        request_id: 요청 추적 ID.
        model_id: 로그용 식별자 (선택).
    """
    if provider is None:
        return
    try:
        await provider.invalidate()
    except Exception as e:
        logger.warning(
            "LLM model cache invalidation failed — will expire by TTL",
            request_id=request_id,
            model_id=model_id,
            error=str(e),
        )
