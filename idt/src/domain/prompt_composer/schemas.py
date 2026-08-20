"""prompt_composer 도메인 VO — 외부 의존 없음(순수 frozen dataclass).

Design Ref: §3.1 / §2.4 P1 — LLM 출력 스키마(`_PromptDraft`)는 이 모듈에 없다.
인프라 어댑터에만 존재하며, 도메인은 그 타입을 모른다.

**겸용하지 않는 이유** (Design §1.3): 선행 사이클의 intent 모듈이 LLM 스키마와
도메인 VO를 겸용했다가 계산 필드가 3개로 늘면서 확장에 실패했다
(`infrastructure/intent/adapter.py:6-10`). 본 모듈의 계산 필드는 4개이고
결과가 DB에 영속되므로 오염값이 되돌릴 수 없게 남는다.
"""
from dataclasses import dataclass

# agent-create-wizard Design Ref: §3.4 — prompt_version.source 의 허용값.
# DB 컬럼값이자 응답 wire 문자열이므로 변경은 곧 계약 파괴다 (V063).
PROMPT_SOURCE_LLM = "llm"
PROMPT_SOURCE_HUMAN = "human"


@dataclass(frozen=True)
class ToolMeta:
    """tool_catalog 1건의 프롬프트용 투영.

    tool_id 는 카탈로그 표기를 그대로 쓴다:
      내부  → ``internal:{tool_id}``
      MCP  → ``mcp:{server_id}:{tool_name}``
    """

    tool_id: str
    name: str
    description: str
    source: str = "internal"  # "internal" | "mcp"
    server_name: str | None = None


@dataclass(frozen=True)
class RoleSection:
    """에이전트가 수행하는 역할 1건.

    Design Q1 — 도구에 종속되지 않는다. 도구가 0개여도 역할은 존재할 수 있다.
    """

    title: str
    detail: str


@dataclass(frozen=True)
class ToolGuide:
    """도구 1건의 사용 지침.

    ``name`` 은 조립 시 표기용이며 카탈로그 값으로 덮어쓴다
    (`PromptAssemblyPolicy.drop_hallucinated`) — LLM 이 도구를 다른 이름으로
    부르는 것을 막는다.
    """

    tool_id: str
    name: str
    when: str
    how: str = ""
    caution: str = ""


@dataclass(frozen=True)
class ContextSection:
    """prompt-depth Design Ref: §3.1 / FR-02 — 제약과 배경.

    `constraints` 는 intent 의 `constraints` 축과 이름이 같지만 같은 값이 아니다.
    LLM 이 목적·도구로부터 도출한 제약도 함께 들어온다.
    """

    constraints: tuple[str, ...] = ()
    background: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSection:
    """prompt-depth Design Ref: §3.1 / FR-03 — 상황 1건에 대한 처리 절차.

    구조를 두는 이유: 조립이 `### {situation}` + 번호 목록으로 실제 소비한다.
    평문이면 "일반 요청일 때 / 모호할 때"의 경계가 사라진다 (Design §2.0 Option C).
    """

    situation: str
    steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptSections:
    """LLM 이 생성하는 7개 섹션 (prompt-depth Design Ref: §3.1).

    Design §2.4 P2 — 계산 필드(degraded 등)를 두지 않는다.

    **필드 순서 = 조립 순서**다 (`PromptAssemblyPolicy.assemble`). 읽는 사람이
    VO 만 보고 출력 순서를 알 수 있게 유지한다.

    신규 4필드는 전부 기본값을 가진다 — 기존 생성자 호출부가 깨지지 않는다.
    `context` 가 `| None` 인 이유: 빈 `ContextSection()` 과 "없음"을 구분해야
    폴백·생략 규칙이 명확해진다.
    """

    purpose: str
    identity: str = ""
    context: ContextSection | None = None
    roles: tuple[RoleSection, ...] = ()
    tool_guides: tuple[ToolGuide, ...] = ()
    workflows: tuple[WorkflowSection, ...] = ()
    style: str = ""
    principles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposedPrompt:
    """생성 결과 + 관측 정보.

    하단 5개 필드는 **시스템만** 채운다. LLM 이 도달할 수 있는 경로가 없다.
    """

    sections: PromptSections
    assembled: str
    degraded: bool = False
    reason: str | None = None
    dropped_tool_ids: tuple[str, ...] = ()
    """후보에 없어 폐기된 tool_id (Design E5)."""
    unknown_tool_ids: tuple[str, ...] = ()
    """카탈로그에 없거나 비활성이라 반영되지 않은 tool_id (Design E6)."""
    elapsed_ms: int = 0
