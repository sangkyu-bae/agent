"""SubAgentContextPolicy: 서브에이전트 입력 조립의 순수 규칙.

Design Ref: subagent-context-scope §3.1/§3.3 (R1~R8).

서브에이전트 워커가 부모 그래프에서 받는 입력 = [원 질문] + [참고 자료] +
[현재 작업]. 이 모듈은 그 판별·상한·라벨 규칙만 갖는다. 메시지 객체(LangChain)
해석과 조립은 application의 전략이 맡는다 — domain은 MessageView(str)만 본다.

QG 피드백 접두는 application 상수라 생성자로 주입받는다 (D-09).
"""
from dataclasses import dataclass

from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy

_ROLE_ALIASES: dict[str, str] = {"human": "user", "assistant": "ai"}


@dataclass(frozen=True)
class MessageView:
    """판별용 메시지 뷰 — 정규화된 역할·워커 이름·본문 문자열."""

    role: str
    name: str
    content: str


@dataclass(frozen=True)
class ReferenceBlock:
    """렌더된 [참고 자료] 블록. 산출이 없으면 text=""."""

    text: str
    item_count: int
    total_chars: int
    truncated: bool


class SubAgentContextPolicy:
    DEFAULT_REFERENCE_MAX_CHARS = 4000

    ORIGIN_LABEL = "[원 질문]"
    REFERENCE_LABEL = "[참고 자료 — 상위 에이전트가 이번 요청에서 이미 수집한 결과]"
    REFERENCE_GUIDE = "아래 자료는 참고용입니다. 필요한 경우에만 다시 수집하세요."
    TASK_LABEL = "[현재 작업]"
    RETRY_LABEL = "[재시도 사유]"
    TRUNCATED_NOTE = "…(절단됨)"
    _ITEM_SEPARATOR = "\n---\n"

    def __init__(
        self,
        feedback_prefixes: tuple[str, ...] = (),
        reference_max_chars: int | None = None,
    ) -> None:
        self._feedback_prefixes = tuple(p for p in feedback_prefixes if p)
        self.reference_max_chars = (
            reference_max_chars
            if reference_max_chars and reference_max_chars > 0
            else self.DEFAULT_REFERENCE_MAX_CHARS
        )

    # ── R1 ────────────────────────────────────────────────────────
    @staticmethod
    def normalize_role(raw: object) -> str:
        """human→user, assistant→ai. 문자열이 아니면 '' (원 질문 후보에서 빠진다)."""
        if not isinstance(raw, str):
            return ""
        return _ROLE_ALIASES.get(raw, raw)

    # ── R2/R3 ─────────────────────────────────────────────────────
    def find_origin_index(self, views: list[MessageView]) -> int | None:
        """이번 턴 사용자 원 질문의 index. QG 피드백·재주입분은 건너뛴다.

        기존 `_current_turn_messages`는 QG 피드백(role=user)을 턴 경계로
        오인한다 — 이 index가 이번 턴 경계의 단일 정의다 (D-05).
        """
        for idx in range(len(views) - 1, -1, -1):
            view = views[idx]
            if view.role != "user":
                continue
            if self._is_feedback(view.content) or self._is_reinjected(view.content):
                continue
            return idx
        return None

    # ── R4 ────────────────────────────────────────────────────────
    def collect_references(
        self,
        views: list[MessageView],
        origin_index: int | None,
        self_worker_id: str,
    ) -> list[MessageView]:
        """경계 이후 다른 워커 산출(이름 있는 AI). 경계를 모르면 빈 목록.

        자기 산출은 제외한다 — 재시도 시 실패 산출을 되먹이지 않고
        사유는 [재시도 사유]로 전달한다 (D-06).
        """
        if origin_index is None:
            return []
        return [
            view for view in views[origin_index + 1:]
            if self._is_reference(view, self_worker_id)
        ]

    def _is_reference(self, view: MessageView, self_worker_id: str) -> bool:
        return (
            view.role == "ai"
            and bool(view.name)
            and view.name != self_worker_id
            and bool(view.content.strip())
            and not self._is_reinjected(view.content)
        )

    # ── R5 ────────────────────────────────────────────────────────
    def render_references(self, refs: list[MessageView]) -> ReferenceBlock:
        """최신 산출부터 예산을 채우고 시간순으로 렌더한다 (D-02)."""
        picked, total, truncated = self._pick_within_budget(refs)
        if not picked:
            return ReferenceBlock(text="", item_count=0, total_chars=0,
                                  truncated=truncated)
        items = self._ITEM_SEPARATOR.join(
            f"[{name} 산출]\n{body}" for name, body in picked
        )
        text = f"{self.REFERENCE_LABEL}\n{self.REFERENCE_GUIDE}\n\n{items}"
        return ReferenceBlock(text=text, item_count=len(picked),
                              total_chars=total, truncated=truncated)

    def _pick_within_budget(
        self, refs: list[MessageView]
    ) -> tuple[list[tuple[str, str]], int, bool]:
        """(시간순 [(name, body)], 실린 본문 글자 수, 절단·드롭 여부)."""
        remaining = self.reference_max_chars
        picked: list[tuple[str, str]] = []
        total = 0
        for view in reversed(refs):
            content = view.content
            if len(content) <= remaining:
                picked.append((view.name, content))
                remaining -= len(content)
                total += len(content)
                continue
            if not picked:
                # 최신 1건이 혼자 상한 초과 — 앞부분만 싣는다.
                picked.append((view.name, content[:remaining] + self.TRUNCATED_NOTE))
                total += remaining
            return list(reversed(picked)), total, True
        return list(reversed(picked)), total, False

    # ── R6/R7 ─────────────────────────────────────────────────────
    def detect_retry_feedback(self, views: list[MessageView]) -> str:
        """마지막 메시지가 QG 피드백이면 그 본문, 아니면 ''.

        QG 재시도는 supervisor를 거치지 않아 worker_task가 유지된다 (Q-D1).
        """
        if not views:
            return ""
        last = views[-1]
        if last.role == "user" and self._is_feedback(last.content):
            return last.content
        return ""

    def compose_task(self, task: str, origin: str, feedback: str) -> str:
        """[현재 작업] 블록.

        과제가 비면 원 질문으로 폴백(FR-06), 재시도면 사유를 덧붙인다(FR-05).
        """
        body = task.strip() or origin
        if feedback:
            body = f"{body}\n\n{self.RETRY_LABEL}\n{feedback}"
        return f"{self.TASK_LABEL}\n{body}"

    def origin_block(self, origin: str) -> str:
        return f"{self.ORIGIN_LABEL}\n{origin}"

    # ── R8 ────────────────────────────────────────────────────────
    @staticmethod
    def summarize(
        *, has_origin: bool, ref: ReferenceBlock, retry: bool, fallback: bool
    ) -> str:
        """step output_summary — 길이·개수만, 본문 값은 싣지 않는다 (FR-07)."""
        if fallback:
            return "서브에이전트 입력: 레거시(마지막 메시지)"
        cut = " (절단)" if ref.truncated else ""
        return (
            f"서브에이전트 입력: 원질문 {'O' if has_origin else 'X'} / "
            f"참고자료 {ref.item_count}건 {ref.total_chars}자{cut} / "
            f"재시도 {'O' if retry else 'X'}"
        )

    # ── helpers ───────────────────────────────────────────────────
    def _is_feedback(self, content: str) -> bool:
        return bool(self._feedback_prefixes) and content.startswith(
            self._feedback_prefixes
        )

    @staticmethod
    def _is_reinjected(content: str) -> bool:
        return AnalysisSnapshotPolicy.is_reinjected(content)
