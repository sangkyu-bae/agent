"""AgentBuilderPolicy, UpdateAgentPolicy, VisibilityPolicy: 에이전트 빌더 도메인 규칙."""
from dataclasses import dataclass
from enum import Enum


class Visibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


SCOPE_TO_VISIBILITY: dict[str, str] = {
    "PERSONAL": "private",
    "DEPARTMENT": "department",
    "PUBLIC": "public",
}

VISIBILITY_RANK: dict[str, int] = {
    "private": 0,
    "department": 1,
    "public": 2,
}


@dataclass(frozen=True)
class AccessCheckInput:
    agent_owner_id: str
    agent_visibility: str
    agent_department_id: str | None
    viewer_user_id: str
    viewer_department_ids: list[str]
    viewer_role: str


class VisibilityPolicy:
    @staticmethod
    def can_access(ctx: AccessCheckInput) -> bool:
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return True
        if ctx.agent_visibility == Visibility.PUBLIC:
            return True
        if ctx.agent_visibility == Visibility.DEPARTMENT:
            return (
                ctx.agent_department_id is not None
                and ctx.agent_department_id in ctx.viewer_department_ids
            )
        return False

    @staticmethod
    def can_edit(ctx: AccessCheckInput) -> bool:
        return ctx.agent_owner_id == ctx.viewer_user_id

    @staticmethod
    def can_delete(ctx: AccessCheckInput) -> bool:
        return (
            ctx.agent_owner_id == ctx.viewer_user_id
            or ctx.viewer_role == "admin"
        )

    @staticmethod
    def max_visibility_for_scopes(scopes: list[str]) -> str:
        if not scopes:
            raise ValueError("scopes must not be empty")
        ranks: list[int] = []
        for scope in scopes:
            vis = SCOPE_TO_VISIBILITY.get(scope)
            if vis is None:
                raise ValueError(f"Unknown scope: {scope}")
            ranks.append(VISIBILITY_RANK[vis])
        min_rank = min(ranks)
        for vis, rank in VISIBILITY_RANK.items():
            if rank == min_rank:
                return vis
        raise ValueError("Unreachable")

    @staticmethod
    def clamp_visibility(requested: str, scopes: list[str]) -> str:
        if not scopes:
            return requested
        max_vis = VisibilityPolicy.max_visibility_for_scopes(scopes)
        if VISIBILITY_RANK[requested] > VISIBILITY_RANK[max_vis]:
            return max_vis
        return requested


class AgentBuilderPolicy:
    MAX_TOOLS = 10
    MAX_SUB_AGENTS = 3
    MAX_WORKERS_TOTAL = 10
    MAX_NAME_LENGTH = 200
    MAX_SYSTEM_PROMPT_LENGTH = 4000
    MAX_USER_REQUEST_LENGTH = 1000

    @classmethod
    def validate_tool_count(cls, count: int) -> None:
        # agent-instruction-required: 도구 자동선택 제거로 0개 허용 (하한 없음, 상한만 검증)
        if count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")

    @classmethod
    def validate_worker_count(cls, workers: list) -> None:
        # agent-instruction-required: 워커 0개(순수 대화형) 허용 (하한 없음)
        if len(workers) > cls.MAX_WORKERS_TOTAL:
            raise ValueError(f"워커는 최대 {cls.MAX_WORKERS_TOTAL}개까지 선택할 수 있습니다.")

        tool_count = sum(1 for w in workers if w.worker_type == "tool")
        sub_agent_count = sum(1 for w in workers if w.worker_type == "sub_agent")

        if tool_count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")
        if sub_agent_count > cls.MAX_SUB_AGENTS:
            raise ValueError(f"서브 에이전트는 최대 {cls.MAX_SUB_AGENTS}개까지 선택할 수 있습니다.")

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        # agent-instruction-required: 지침 필수 (자동생성은 Fix 에이전트 전담)
        if not prompt or not prompt.strip():
            raise ValueError(
                "지침(system_prompt)은 비어 있을 수 없습니다. "
                "직접 입력하거나 Fix 에이전트로 초안을 생성해 주세요."
            )
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LENGTH:
            raise ValueError(
                f"system_prompt는 {cls.MAX_SYSTEM_PROMPT_LENGTH}자를 초과할 수 없습니다."
            )

    @classmethod
    def validate_name(cls, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("name은 비어 있을 수 없습니다.")
        if len(name) > cls.MAX_NAME_LENGTH:
            raise ValueError(f"name은 {cls.MAX_NAME_LENGTH}자를 초과할 수 없습니다.")


class ForkPolicy:
    @staticmethod
    def can_fork(ctx: AccessCheckInput) -> bool:
        """포크 가능 여부: 접근 가능 + 자신의 에이전트가 아닌 경우."""
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return False
        return VisibilityPolicy.can_access(ctx)

    @staticmethod
    def validate_source_status(status: str) -> None:
        """삭제된 에이전트는 포크 불가."""
        if status == "deleted":
            raise ValueError("삭제된 에이전트는 포크할 수 없습니다.")


class IterationLimitPolicy:
    """supervisor 반복 한도 도메인 규칙 (agent-recursion-limit D2).

    한도의 단위는 supervisor 반복 횟수(SupervisorState.iteration_count).
    LangGraph recursion_limit은 이 값에서 파생하며, 최악 경로(반복당
    supervisor+worker+chart_router+chart_builder+quality_gate = 5스텝,
    quality_gate 재시도 시 반복당 최대 +8스텝)보다 항상 크게 잡아
    state 가드가 먼저 발동하게 한다. 계수 변경은 이 클래스 상수만 수정.
    """

    DEFAULT = 25
    MIN = 10
    MAX = 1000

    RECURSION_STEP_FACTOR = 10
    RECURSION_BUFFER = 20

    SUB_AGENT_DIVISOR = 2
    SUB_AGENT_MIN = 5

    @classmethod
    def validate(cls, value: int) -> None:
        if not (cls.MIN <= value <= cls.MAX):
            raise ValueError(
                f"max_iterations는 {cls.MIN}~{cls.MAX} 범위여야 합니다. "
                f"(입력값: {value})"
            )

    @classmethod
    def derive_recursion_limit(cls, max_iterations: int) -> int:
        return max_iterations * cls.RECURSION_STEP_FACTOR + cls.RECURSION_BUFFER

    @classmethod
    def sub_agent_limit(cls, parent_max_iterations: int) -> int:
        return max(
            parent_max_iterations // cls.SUB_AGENT_DIVISOR, cls.SUB_AGENT_MIN
        )


class QualityGatePolicy:
    """워커 응답 품질 검증 도메인 규칙."""

    MIN_RESPONSE_LENGTH = 10
    EMPTY_INDICATORS = ["모르겠습니다", "답변할 수 없습니다", "정보를 찾을 수 없"]

    @classmethod
    def check_response(cls, content: str) -> bool:
        if not content or len(content.strip()) < cls.MIN_RESPONSE_LENGTH:
            return False

        stripped = content.strip().lower()
        for indicator in cls.EMPTY_INDICATORS:
            if stripped.startswith(indicator):
                return False

        return True


class SearchPipelinePolicy:
    """search 노드 파이프라인 도메인 규칙 (search-node-query-pipeline).

    순수 규칙만 보관 — LLM/도구 호출 없음.
    """

    MAX_SEARCH_ATTEMPTS = 3            # 최초 1 + 재시도 2
    DEFAULT_COMPRESS_THRESHOLD = 4000  # 압축 발동 임계 길이(자)

    def __init__(self, compress_threshold: int | None = None) -> None:
        self.compress_threshold = (
            compress_threshold
            if compress_threshold and compress_threshold > 0
            else self.DEFAULT_COMPRESS_THRESHOLD
        )

    def is_last_attempt(self, attempt: int) -> bool:
        """attempt(1-base)가 마지막 시도인가 — True면 validate 생략 (Design D1)."""
        return attempt >= self.MAX_SEARCH_ATTEMPTS

    def needs_compression(self, text: str) -> bool:
        return len(text) > self.compress_threshold


class CollectPipelinePolicy:
    """collect 노드 도메인 규칙 (mcp-tool-category-routing §3.1).

    순수 규칙만 보관 — LLM/도구 호출 없음. SearchPipelinePolicy와 동형이되
    '시도 횟수' 개념이 없다: collect는 도구를 정확히 1회 호출하는 단일샷이며,
    이 계약은 설정으로 바뀌지 않는다(TOOL_CALLS_PER_RUN 상수).
    """

    # 단일샷 계약 — react 루프 부재의 근거. 변경 금지(설정 대상 아님).
    TOOL_CALLS_PER_RUN = 1
    # 압축 발동 임계 길이(자). search 파이프라인과 같은 기준을 쓴다 —
    # 두 노드의 산출이 같은 근거 블록으로 소비되므로 길이 정책이 갈리면
    # 하류 컨텍스트 예산이 노드 종류에 따라 들쭉날쭉해진다.
    DEFAULT_COMPRESS_THRESHOLD = 4000

    def __init__(self, compress_threshold: int | None = None) -> None:
        self.compress_threshold = (
            compress_threshold
            if compress_threshold and compress_threshold > 0
            else self.DEFAULT_COMPRESS_THRESHOLD
        )

    def needs_compression(self, text: str) -> bool:
        """FR-09: 임계치를 넘을 때만 압축 — 짧은 수집물은 무손실 통과."""
        return len(text) > self.compress_threshold


class ToolCallBudgetPolicy:
    """react 워커의 도구 호출 예산 (mcp-tool-category-routing §5 D-05).

    미분류(react) 워커가 워커 1회 실행당 도구를 몇 번까지 부를 수 있는지
    정한다. 기본 2회인 이유: 1차 호출이 ToolArgumentPolicy에 차단되면
    워커가 차단 메시지를 받아 스스로 교정할 기회가 정확히 한 번 필요하다.
    """

    DEFAULT_RUN_LIMIT = 2
    MIN_RUN_LIMIT = 1
    MAX_RUN_LIMIT = 20

    @classmethod
    def resolve(cls, max_tool_calls: int | None) -> int:
        """카탈로그 지정값을 해석한다. 없거나 범위 밖이면 기본값으로 클램프.

        Args:
            max_tool_calls: tool_catalog.max_tool_calls (None 허용)

        Returns:
            실제 적용할 run_limit
        """
        if max_tool_calls is None or isinstance(max_tool_calls, bool):
            return cls.DEFAULT_RUN_LIMIT
        if not isinstance(max_tool_calls, int):
            return cls.DEFAULT_RUN_LIMIT
        if max_tool_calls < cls.MIN_RUN_LIMIT:
            return cls.MIN_RUN_LIMIT
        if max_tool_calls > cls.MAX_RUN_LIMIT:
            return cls.MAX_RUN_LIMIT
        return max_tool_calls


class ToolErrorPolicy:
    """react 워커 트레이스의 도구 오류 식별 — 결정적 신호만 담당 (wiki-guided-routing D4).

    Design Ref: D4 — 도구 오류(ToolMessage)는 워커 내부 트레이스에만 남고 supervisor
    state에는 LLM이 쓴 문장만 올라간다. 확실한 신호(오류 status·오류 접두어)는 여기서
    결정적으로 뽑고, 그 후 판단(위키 재확인·되묻기)은 LLM이 한다.
    LangChain 타입을 참조하지 않는다 — type/status/content 속성만 duck typing.
    """

    # langchain-mcp-adapters 오류 응답 형식(실측: 런 8ccc097f, 153bebce).
    ERROR_PREFIXES: tuple[str, ...] = ("Error executing tool",)
    MAX_SUMMARY_CHARS = 200

    @classmethod
    def summarize(cls, messages: list) -> str:
        """첫 도구 오류의 요약(첫 줄, 상한 절단). 없으면 ''."""
        for msg in messages or ():
            if getattr(msg, "type", None) != "tool":
                continue
            content = getattr(msg, "content", "")
            text = content if isinstance(content, str) else str(content)
            if cls._is_error(getattr(msg, "status", None), text):
                return text.splitlines()[0][: cls.MAX_SUMMARY_CHARS] if text else "error"
        return ""

    @classmethod
    def _is_error(cls, status, text: str) -> bool:
        if status == "error":
            return True
        return text.lstrip().startswith(cls.ERROR_PREFIXES)


class EmptyResultPolicy:
    """수집 산출의 '유효 데이터 부재' 판정 — 결정적 신호만 담당.

    Design Ref: supervisor-early-finish-fix §3.2 (D-07).

    ToolErrorPolicy와 같은 역할 분담: 확실한 신호는 여기서 결정적으로 뽑고,
    '그래서 무엇을 할 것인가'는 supervisor LLM이 판단한다(그래프 계약 ③).
    도구 성공(오류 아님) + 유효 데이터 없음을 오류와 구분해 식별한다.
    LangChain 타입을 참조하지 않는다 — 문자열만 받는다.

    판정 재현율 주의: 네비게이션이 긴 페이지는 본문 길이가 충분해 1차(구조적)로
    잡히지 않고 2차(패턴)로만 잡힌다(실측: 트레이스 01a0a82b). 그래서 패턴은
    코드 상수가 아니라 설정값으로 주입받는다.
    """

    MAX_SUMMARY_CHARS = 120
    # 1차 구조적 신호 — 산출이 이보다 짧으면 수집 자체가 비었다고 본다.
    MIN_BODY_CHARS = 200

    _REASON_NO_BODY = "수집 산출이 비어 있음"
    _REASON_NO_DATA = "수집 산출에 유효 데이터 영역이 없음"

    @classmethod
    def detect(cls, body, patterns) -> str:
        """빈 결과면 사유 요약을, 아니면 ''을 돌려준다.

        Args:
            body: 워커 산출 본문. str이 아니면 판정을 생략한다(§6.1).
            patterns: 빈 결과 보조 문구. None/빈 튜플이면 1차만 동작한다.

        Returns:
            사유 요약(MAX_SUMMARY_CHARS 이내). 정상이면 ''.
            수집 원문을 담지 않는다 — 외부 콘텐츠의 지시문 승격 방지(§7).
        """
        if not isinstance(body, str):
            return ""
        if len(body.strip()) < cls.MIN_BODY_CHARS:
            return cls._REASON_NO_BODY[: cls.MAX_SUMMARY_CHARS]
        for pattern in patterns or ():
            if pattern and pattern in body:
                return cls._REASON_NO_DATA[: cls.MAX_SUMMARY_CHARS]
        return ""


class UpdateAgentPolicy:
    @classmethod
    def validate_update(cls, status: str, system_prompt: str | None) -> None:
        if status != "active":
            raise ValueError("비활성화된 에이전트는 수정할 수 없습니다.")
        if system_prompt is not None:
            AgentBuilderPolicy.validate_system_prompt(system_prompt)


# ── Multi-Agent Composition Policies ──────────────────────────


class CircularReferenceError(ValueError):
    """에이전트 참조 순환 발생."""

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        path_str = " → ".join(cycle_path)
        super().__init__(f"순환참조가 감지되었습니다: {path_str}")


class NestingDepthExceededError(ValueError):
    """중첩 깊이 초과."""

    def __init__(self, current_depth: int, max_depth: int) -> None:
        super().__init__(
            f"중첩 깊이 {current_depth}이(가) 최대 허용 깊이 {max_depth}을(를) 초과합니다"
        )


class CircularReferencePolicy:
    """에이전트 간 순환참조 방지 정책."""

    @staticmethod
    def validate_no_cycle(current_agent_id: str, visited: set[str]) -> None:
        if current_agent_id in visited:
            cycle = list(visited) + [current_agent_id]
            raise CircularReferenceError(cycle)


class NestingDepthPolicy:
    """에이전트 중첩 깊이 제한 정책."""

    MAX_NESTING_DEPTH = 2

    @classmethod
    def validate_depth(cls, current_depth: int) -> None:
        if current_depth > cls.MAX_NESTING_DEPTH:
            raise NestingDepthExceededError(current_depth, cls.MAX_NESTING_DEPTH)


class SubAgentAccessPolicy:
    """[DEPRECATED] 구독 기반 서브에이전트 사용 권한 정책.

    DD-1(agent-subagent-management) 이후 서브에이전트 접근은 가시성 기반
    `VisibilityPolicy.can_access`로 일원화되었다. 이 정책은 더 이상 호출되지 않으며
    (dead code), 하위 호환/회귀 테스트 보존 목적으로만 남겨 둔다. 신규 코드에서
    사용하지 말 것.
    """

    @staticmethod
    def can_use_as_sub_agent(
        parent_owner_id: str,
        sub_agent_owner_id: str,
        is_subscribed: bool,
    ) -> bool:
        if parent_owner_id == sub_agent_owner_id:
            return True
        return is_subscribed


class GatedWorkerPolicy:
    """approval-gate Plan FR-05 — 승인 게이트 도구의 단독 워커 제약.

    Design Ref: §2.0 / §7.2. 승인 도구를 다른 도구와 같은 워커에 두면
    react 루프 중간에 게이트가 걸려, 앞서 실행된 도구 결과가 재개 시
    유실된다(재개 단위는 '워커 1홉'). 구성을 제약해 그 상황 자체를 없앤다 —
    게이트는 항상 워커의 유일한 도구가 된다.

    프롬프트로 타이르는 대신 생성 시점에 구조로 막는다
    (위키 builtin-tools-optout-channel §4 와 같은 계열).
    """

    @staticmethod
    def collect_gated_tool_ids(catalog_meta: dict | None) -> set[str]:
        """카탈로그에서 승인 대상 tool_id 집합을 뽑는다.

        카탈로그 미주입·조회 실패(None/빈 dict)면 빈 집합 — 이 사이클
        이전과 동일하게 동작한다(mcp-tool-category-routing FR-14 취지).
        """
        return {
            tool_id
            for tool_id, entry in (catalog_meta or {}).items()
            if getattr(entry, "requires_approval", False)
        }

    @staticmethod
    def validate(workers: list, gated_tool_ids: set[str]) -> None:
        """워커 구성 검증. 위반 시 ValueError.

        빌트인 주입 **후**에 호출해야 한다 — 주입으로 제약이 깨질 수 있다.
        """
        if not gated_tool_ids:
            return
        by_worker: dict[str, list[str]] = {}
        for worker in workers:
            # 서브에이전트는 도구가 아니라 중첩 그래프다. 자체 게이트를
            # 가지므로 이 제약의 대상이 아니다.
            if getattr(worker, "worker_type", "tool") != "tool":
                continue
            by_worker.setdefault(worker.worker_id, []).append(worker.tool_id)

        for worker_id, tool_ids in by_worker.items():
            gated = [t for t in tool_ids if t in gated_tool_ids]
            if gated and len(tool_ids) > 1:
                raise ValueError(
                    f"승인이 필요한 도구 {gated}는 워커 '{worker_id}'에 단독으로만 "
                    f"배치할 수 있습니다 (현재 {tool_ids}). "
                    f"수집 워커와 발송 워커를 분리하면 supervisor가 순차로 "
                    f"라우팅합니다."
                )


# ── action-category-compose-node ─────────────────────────────────


class ActionArgumentPolicy:
    """action 워커의 발송 인자 규칙 — 본문 키 해석·병합·요약.

    Design Ref: action-category-compose-node §3.1 / D-04 / D-09.
    순수 dict·str 규칙만 다룬다(외부 의존 없음).
    """

    # gate_middleware._DRAFT_KEYS 와 같은 순서 — 승인 화면의 초안 추출과 일치.
    DRAFT_KEY_CANDIDATES: tuple[str, ...] = ("draft", "body", "content", "본문")

    @classmethod
    def resolve_draft_key(cls, configured: str, input_schema: dict | None) -> str:
        """초안을 넣을 인자 키를 확정한다.

        설정 키가 있으면 스키마에 존재해야 하고, 비어 있으면 후보 순서로
        스키마에 있는 첫 키를 고른다. 둘 다 실패하면 ValueError —
        compile 시 워커 격리 사유가 된다(D-09). 스키마를 모르면 키 이름을
        추측하게 되므로 역시 실패로 본다.
        """
        properties = (input_schema or {}).get("properties")
        if not isinstance(properties, dict) or not properties:
            raise ValueError("도구 입력 스키마에 properties가 없어 본문 키를 정할 수 없습니다")
        key = (configured or "").strip()
        if key:
            if key not in properties:
                raise ValueError(
                    f"설정된 draft_arg_key {key!r}가 도구 입력 스키마에 없습니다 "
                    f"(스키마 키: {sorted(properties)})"
                )
            return key
        for candidate in cls.DRAFT_KEY_CANDIDATES:
            if candidate in properties:
                return candidate
        raise ValueError(
            "draft_arg_key가 비어 있고 관례 키"
            f"{list(cls.DRAFT_KEY_CANDIDATES)}도 스키마에 없습니다 "
            f"(스키마 키: {sorted(properties)})"
        )

    @staticmethod
    def merge(arguments: dict | None, draft_key: str, draft: str) -> dict:
        """복사본에 arguments[draft_key] = draft. 마지막 덮어쓰기 — 초안이 이긴다 (D-04)."""
        merged = dict(arguments or {})
        merged[draft_key] = draft
        return merged

    @staticmethod
    def summarize_keys(arguments: dict | None) -> list[str]:
        """로그·스텝 요약용 키 목록. 값은 절대 싣지 않는다 (Plan FR-24/25)."""
        return sorted(str(k) for k in (arguments or {}).keys())


@dataclass(frozen=True)
class DraftContext:
    """final_answer 초안 보존 모드의 입력 — 마지막 초안과 그 집행 결과."""

    worker_id: str
    draft: str
    outcome: str


class FinalAnswerDraftPolicy:
    """final_answer 초안 보존 모드 — 감지·블록·지시를 한 곳이 소유한다.

    Design Ref: action-category-compose-node §3.1 / D-07 / Plan FR-17·FR-18.
    이 클래스가 final_answer 초안 처리의 유일한 교체 지점이다. 예컨대
    "초안은 LLM을 거치지 않고 프로그램적으로 삽입"으로 바꾸려면 이 정책만
    바꾸고 노드는 그대로 둔다.
    """

    _EMPTY_DRAFT_NOTICE = "(작성된 초안 없음 — 아래 집행 결과의 사유를 그대로 전달하세요)"

    @staticmethod
    def detect(
        draft_sections: list[tuple[str, str, str]],
        later_outputs: dict[str, str] | None = None,
    ) -> DraftContext | None:
        """(worker_id, draft, outcome) 목록 → 마지막 초안 컨텍스트. 없으면 None.

        later_outputs: worker_id → 초안 메시지 이후에 같은 워커 이름으로 들어온
        산출(재개 시 _restore_state 가 주입한 집행 결과). 있으면 초안 메시지
        안의 outcome("승인 대기…")보다 우선한다(D-07).
        """
        if not draft_sections:
            return None
        worker_id, draft, outcome = draft_sections[-1]
        override = (later_outputs or {}).get(worker_id)
        if override:
            outcome = override
        return DraftContext(worker_id=worker_id, draft=draft, outcome=outcome)

    @classmethod
    def render_block(cls, ctx: DraftContext) -> str:
        """시스템 프롬프트에 붙일 블록. 초안은 한 글자도 바꾸지 않고 싣는다."""
        draft = ctx.draft if ctx.draft.strip() else cls._EMPTY_DRAFT_NOTICE
        return (
            "[작성된 초안 — 원문 그대로 포함할 것]\n"
            f"{draft}\n\n"
            "[집행 결과]\n"
            f"{ctx.outcome}"
        )

    @staticmethod
    def instruction() -> str:
        """user tail 지시 — 재작성 금지."""
        return (
            "위 [작성된 초안]을 한 글자도 고치지 말고 그대로 답변에 포함하고, "
            "[집행 결과]를 사용자에게 보고하세요. 초안을 요약·수정·재작성하지 마세요."
        )
