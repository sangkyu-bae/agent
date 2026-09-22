"""승인 게이트 도구의 단독 워커 제약 검증 — 생성·수정 경로 공용.

approval-gate Plan FR-05 / Check G10. 처음엔 생성 경로(CreateAgentUseCase)에만
있어서, 생성 후 **수정**으로 게이트 도구를 다른 도구와 같은 워커에 묶을 수
있었다. 두 경로가 같은 규칙을 쓰도록 여기로 추출한다.

판정 규칙은 도메인 GatedWorkerPolicy 가 소유하고, 이 모듈은 카탈로그를 읽어
승인 대상 tool_id 집합을 만드는 배선만 한다.
"""
from src.domain.agent_builder.policies import GatedWorkerPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


async def validate_gated_workers(
    tool_catalog_repo, workers: list, request_id: str, logger: LoggerInterface
) -> None:
    """위반 시 ValueError. 빌트인 주입 **후**에 호출해야 한다.

    카탈로그 미주입·조회 실패 시 검증을 건너뛴다(빈 집합 → no-op): 승인 대상
    여부를 모르는 상태에서 저장을 막으면 카탈로그 장애가 에이전트 저장 전체를
    세운다. 게이트 자체도 같은 조건에서 미부착이라 판정 기준이 어긋나지 않는다.
    """
    if tool_catalog_repo is None:
        return
    try:
        entries = await tool_catalog_repo.list_active(request_id)
    except Exception as e:
        logger.warning(
            "tool catalog load failed — gated worker validation skipped",
            request_id=request_id, exception=e,
        )
        return
    gated = {e.tool_id for e in entries if getattr(e, "requires_approval", False)}
    # 카탈로그는 내부 도구를 `internal:{id}`로, agent_tool 은 `{id}`로 저장한다.
    gated |= {t.split(":")[-1] for t in gated}
    GatedWorkerPolicy.validate(workers, gated)
