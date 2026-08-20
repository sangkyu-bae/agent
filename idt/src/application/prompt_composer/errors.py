"""prompt_composer 애플리케이션 예외 — 라우터가 HTTP 상태로 매핑한다.

Design Ref: §4.1~§4.3 · E9.

여기서 `HTTPException` 을 쓰지 않는 이유: application 계층이 FastAPI 를 알면
레이어 규칙이 깨진다. 상태 코드 결정은 interfaces 의 책임이다.
"""


class PromptComposerError(Exception):
    """이 모듈의 애플리케이션 예외 기반 클래스."""


class PromptSessionNotFoundError(PromptComposerError):
    """세션이 없거나 타인 소유 → 404.

    403 이 아니라 404 인 이유(Design SC-07): 타인 세션의 **존재 여부**를
    노출하지 않기 위해서다.
    """


class AgentAlreadyBoundError(PromptComposerError):
    """이미 agent_id 가 바인딩된 세션에 재바인딩 시도 → 409."""
