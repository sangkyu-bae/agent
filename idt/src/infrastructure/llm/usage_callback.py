"""UsageCallback: LangChain LLM + Tool 호출 단일 인터셉트.

AGENT-OBS-001 §4-3 / §14-1 / §14-3 (M1: LLM hooks):
Supervisor / Worker / Summarizer / 툴 내부 LLM 호출을 모두 단일 지점에서 수집.
provider별 usage_metadata 차이를 정규화한다 (OpenAI / Anthropic / Ollama).

AGENT-OBS-002 §4 (M2: Tool hooks):
LangChain on_tool_start/end/error 비동기 훅을 통해 모든 BaseTool 호출을 자동
인터셉트하여 ai_tool_call 테이블에 영속화한다. 툴 내부 LLM 호출은
_current_tool_call_id 컨텍스트를 통해 ai_llm_call.tool_call_id 로 자동 연결된다.

생명주기 (§4-4):
1. RunAgentUseCase.execute()에서 인스턴스 생성 후 config.callbacks 에 주입
2. (M2) LangChain이 on_tool_start → on_tool_end/error 를 자동 호출
3. LangChain이 on_llm_start/on_llm_end/on_llm_error를 자동 호출
4. on_llm_end에서 tracker.record_llm_call() 호출 (best-effort)
"""
import json
import time
from dataclasses import dataclass
from typing import Any, Final, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from src.application.agent_run.context import (
    get_current_run_context,
    set_current_run_context,
    with_tool_call_id,
)
from src.application.agent_run.purpose_inference import infer_tool_purpose
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import RunId, RunPurpose, TokenUsage
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# M2 — arguments_json / result_summary 컷오프 상수 (Design §4-4)
_ARGS_MAX_BYTES: Final[int] = 1024
_RESULT_MAX_CHARS: Final[int] = 1024
_ERROR_TEXT_MAX_CHARS: Final[int] = 1024


@dataclass(frozen=True)
class _ToolStartInfo:
    """on_tool_start ↔ on_tool_end/error 매칭용 메타 (Design §4-2).

    tool_call_id="" 는 record_tool_call 실패를 나타내는 sentinel.
    on_tool_end에서 이 sentinel을 보면 update_tool_call을 호출하지 않는다.
    """

    tool_call_id: str
    t0: float
    prev_purpose: Optional[RunPurpose]
    prev_tool_call_id: Optional[str]


def _sanitize_args(payload: Any) -> Optional[dict]:
    """LangChain on_tool_start의 inputs/input_str → JSON-safe dict (Design §4-4).

    Rules:
      - None → None
      - dict → 그대로 (단, json.dumps 실패 시 default=str)
      - str → {"input": str}
      - 그 외 → {"input": str(value)}
    1KB(bytes) 초과 시 input 키로 통합하여 truncate.
    어떤 경우에도 raise하지 않는다 (best-effort).
    """
    if payload is None:
        return None
    try:
        if isinstance(payload, dict):
            raw: dict = payload
        elif isinstance(payload, str):
            raw = {"input": payload}
        else:
            raw = {"input": str(payload)}
        try:
            serialized = json.dumps(raw, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = json.dumps(
                {"input": repr(payload)}, ensure_ascii=False
            )
        if len(serialized.encode("utf-8")) <= _ARGS_MAX_BYTES:
            return json.loads(serialized)
        # 컷: input 키로 통합 + 마지막에 truncated 마커
        truncated_value = serialized[: _ARGS_MAX_BYTES - 32]
        return {"input": truncated_value, "_truncated": True}
    except Exception:  # noqa: BLE001 — best-effort
        return None


def _summarize_tool_output(value: Any) -> Optional[str]:
    """tool 반환값 → result_summary 문자열 (1KB 컷, Design §4-4).

    Rules:
      - None → None
      - LangChain Document (page_content 보유) → page_content[:1024]
      - Pydantic BaseModel (model_dump 보유) → json.dumps(model_dump())[:1024]
      - str → str[:1024]
      - dict/list/tuple → json.dumps(..., default=str)[:1024]
      - 그 외 → str(value)[:1024]
    어떤 경우에도 raise하지 않는다.
    """
    if value is None:
        return None
    try:
        if hasattr(value, "page_content"):
            return str(value.page_content)[:_RESULT_MAX_CHARS]
        if hasattr(value, "model_dump"):
            return json.dumps(
                value.model_dump(), ensure_ascii=False, default=str
            )[:_RESULT_MAX_CHARS]
        if isinstance(value, str):
            return value[:_RESULT_MAX_CHARS]
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, default=str)[
                :_RESULT_MAX_CHARS
            ]
        return str(value)[:_RESULT_MAX_CHARS]
    except Exception:  # noqa: BLE001 — best-effort
        return None


def _extract_tool_name(serialized: Any) -> str:
    """LangChain serialized dict에서 tool_name 추출 (Design §4-5)."""
    if not isinstance(serialized, dict):
        return "unknown"
    name = serialized.get("name")
    if isinstance(name, str) and name:
        return name
    ids = serialized.get("id")
    if isinstance(ids, list) and ids:
        last = ids[-1]
        if isinstance(last, str) and last:
            return last
    return "unknown"


def _update_run_context_tool_call_id(tool_call_id: Optional[str]) -> None:
    """활성 RunContext의 tool_call_id를 갱신 (M4 RAG 어댑터 사전 작업, Design §4-5).

    RunContext가 미세팅 상태면 no-op. ContextVar 토큰은 의도적으로 보관하지 않고
    덮어쓰기 방식으로 운영한다 — 한 graph 실행 내내 동일 ctx를 공유하므로
    on_tool_end에서 None으로 다시 set하면 자연스럽게 복원된다.
    """
    ctx = get_current_run_context()
    if ctx is None:
        return
    set_current_run_context(with_tool_call_id(ctx, tool_call_id))


class UsageCallback(AsyncCallbackHandler):
    """LangChain LLM 호출 인터셉트 → RunTracker.record_llm_call."""

    def __init__(
        self,
        tracker: RunTracker,
        run_id: RunId,
        user_id: str,
        agent_id: str,
        logger: LoggerInterface,
    ) -> None:
        self._tracker = tracker
        self._run_id = run_id
        self._user_id = user_id
        self._agent_id = agent_id
        self._logger = logger
        # 현재 활성 step / tool / purpose (노드/툴 진입 시 set)
        self._current_step_id: Optional[str] = None
        self._current_tool_call_id: Optional[str] = None
        self._current_purpose: Optional[RunPurpose] = None
        # M3: ai_run_step.step_index 발급용 monotonic counter (run 내에서 1부터 단조 증가)
        self._step_index: int = 0
        # LangChain run_id (UUID) → on_llm_start 시각
        self._start_ts: dict[UUID, float] = {}
        # M2: LangChain on_tool_start ↔ on_tool_end/error 매칭용
        self._tool_starts: dict[UUID, _ToolStartInfo] = {}

    # ── 컨텍스트 setter (Design §14-1: 노드/툴 진입 시 명시 호출 의무) ──
    def set_purpose(self, purpose: Optional[RunPurpose]) -> None:
        self._current_purpose = purpose

    def enter_step(self, step_id: str) -> None:
        self._current_step_id = step_id
        # M3: step_index monotonic increment (run 내 단조 증가, exit에서 reset 안 함)
        self._step_index += 1

    def exit_step(self) -> None:
        self._current_step_id = None
        # M3: _step_index는 reset하지 않음 — quality_gate retry로 노드 재방문 시
        # step_index 시퀀스 충돌 방지 (Design §4.4)

    def enter_tool(self, tool_call_id: str) -> None:
        self._current_tool_call_id = tool_call_id

    def exit_tool(self) -> None:
        self._current_tool_call_id = None

    # ── LangChain CallbackHandler hooks ────────────────────────────────
    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._start_ts[run_id] = time.monotonic()

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # ChatModel은 on_chat_model_start로 들어오므로 동일 처리
        self._start_ts[run_id] = time.monotonic()

    async def on_llm_end(
        self, response: LLMResult, *, run_id: UUID, **kwargs: Any
    ) -> None:
        latency_ms = self._compute_latency_ms(run_id)
        provider, model_name = self._extract_model(response, kwargs)
        token_usage = self._extract_tokens(response, provider)
        try:
            await self._tracker.record_llm_call(
                run_id=self._run_id,
                step_id=self._current_step_id,
                tool_call_id=self._current_tool_call_id,
                user_id=self._user_id,
                agent_id=self._agent_id,
                provider=provider,
                model_name=model_name,
                purpose=self._current_purpose,
                token_usage=token_usage,
                latency_ms=latency_ms,
                status="SUCCESS",
            )
        except Exception as e:
            self._logger.warning(
                "UsageCallback on_llm_end record failed",
                exception=e,
                run_id=self._run_id.value,
            )

    # ── M2: Tool hooks (Design §4-1 ~ §4-5) ───────────────────────────
    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """툴 호출 시작 인터셉트. record_tool_call → 컨텍스트 갱신."""
        tool_name = _extract_tool_name(serialized)
        args_payload: Any = inputs if inputs is not None else input_str
        arguments = _sanitize_args(args_payload)
        t0 = time.perf_counter()
        prev_purpose = self._current_purpose
        prev_tool_call_id = self._current_tool_call_id
        tool_call_id: Optional[str] = None
        try:
            tool_call_id = await self._tracker.record_tool_call(
                run_id=self._run_id,
                step_id=self._current_step_id,
                tool_name=tool_name,
                arguments=arguments,
                status="STARTED",
            )
        except Exception as e:  # noqa: BLE001 — best-effort
            self._logger.warning(
                "UsageCallback on_tool_start record_tool_call failed",
                exception=e,
                run_id=self._run_id.value,
                tool_name=tool_name,
                lc_run_id=str(run_id),
            )
        # tool_call_id가 None/실패여도 _tool_starts에 sentinel("")로 등록하여
        # on_tool_end의 매칭 미스 경고를 방지하고 컨텍스트 복원은 정상 수행
        self._tool_starts[run_id] = _ToolStartInfo(
            tool_call_id=tool_call_id or "",
            t0=t0,
            prev_purpose=prev_purpose,
            prev_tool_call_id=prev_tool_call_id,
        )
        if tool_call_id is not None:
            self._current_tool_call_id = tool_call_id
            self.set_purpose(infer_tool_purpose(tool_name))
            _update_run_context_tool_call_id(tool_call_id)

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """툴 호출 성공 종료. update_tool_call(SUCCESS) + 컨텍스트 복원."""
        info = self._tool_starts.pop(run_id, None)
        if info is None:
            self._logger.warning(
                "UsageCallback on_tool_end without matching start",
                run_id=self._run_id.value,
                lc_run_id=str(run_id),
            )
            return
        latency_ms = int((time.perf_counter() - info.t0) * 1000)
        if info.tool_call_id:
            try:
                await self._tracker.update_tool_call(
                    tool_call_id=info.tool_call_id,
                    run_id=self._run_id,
                    status="SUCCESS",
                    result_summary=_summarize_tool_output(output),
                    latency_ms=latency_ms,
                )
            except Exception as e:  # noqa: BLE001 — best-effort
                self._logger.warning(
                    "UsageCallback on_tool_end update_tool_call failed",
                    exception=e,
                    run_id=self._run_id.value,
                    tool_call_id=info.tool_call_id,
                )
        self._current_tool_call_id = info.prev_tool_call_id
        self.set_purpose(info.prev_purpose)
        _update_run_context_tool_call_id(info.prev_tool_call_id)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """툴 호출 실패. update_tool_call(FAILED) + 컨텍스트 복원."""
        info = self._tool_starts.pop(run_id, None)
        if info is None:
            self._logger.warning(
                "UsageCallback on_tool_error without matching start",
                run_id=self._run_id.value,
                lc_run_id=str(run_id),
            )
            return
        latency_ms = int((time.perf_counter() - info.t0) * 1000)
        error_text: Optional[str] = (
            str(error)[:_ERROR_TEXT_MAX_CHARS] if error else None
        )
        if info.tool_call_id:
            try:
                await self._tracker.update_tool_call(
                    tool_call_id=info.tool_call_id,
                    run_id=self._run_id,
                    status="FAILED",
                    latency_ms=latency_ms,
                    error_text=error_text,
                )
            except Exception as e:  # noqa: BLE001 — best-effort
                self._logger.warning(
                    "UsageCallback on_tool_error update_tool_call failed",
                    exception=e,
                    run_id=self._run_id.value,
                    tool_call_id=info.tool_call_id,
                )
        self._current_tool_call_id = info.prev_tool_call_id
        self.set_purpose(info.prev_purpose)
        _update_run_context_tool_call_id(info.prev_tool_call_id)

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        latency_ms = self._compute_latency_ms(run_id)
        provider, model_name = self._extract_model_from_kwargs(kwargs)
        try:
            await self._tracker.record_llm_call(
                run_id=self._run_id,
                step_id=self._current_step_id,
                tool_call_id=self._current_tool_call_id,
                user_id=self._user_id,
                agent_id=self._agent_id,
                provider=provider,
                model_name=model_name,
                purpose=self._current_purpose,
                token_usage=TokenUsage(),
                latency_ms=latency_ms,
                status="FAILED",
                error_text=str(error)[:1024],
            )
        except Exception as e:
            self._logger.warning(
                "UsageCallback on_llm_error record failed",
                exception=e,
                run_id=self._run_id.value,
            )

    # ── helpers ────────────────────────────────────────────────────────
    def _compute_latency_ms(self, run_id: UUID) -> Optional[int]:
        start = self._start_ts.pop(run_id, None)
        if start is None:
            return None
        return int((time.monotonic() - start) * 1000)

    def _extract_model(
        self, response: LLMResult, kwargs: dict[str, Any]
    ) -> tuple[str, str]:
        llm_output = response.llm_output or {}
        model_name = (
            llm_output.get("model_name")
            or llm_output.get("model")
            or kwargs.get("invocation_params", {}).get("model")
            or "unknown"
        )
        provider = self._infer_provider(model_name, llm_output)
        return provider, model_name

    def _extract_model_from_kwargs(
        self, kwargs: dict[str, Any]
    ) -> tuple[str, str]:
        invocation = kwargs.get("invocation_params", {}) or {}
        model_name = invocation.get("model") or invocation.get("model_name") or "unknown"
        provider = self._infer_provider(model_name, {})
        return provider, model_name

    def _infer_provider(
        self, model_name: str, llm_output: dict[str, Any]
    ) -> str:
        if "provider" in llm_output:
            return llm_output["provider"]
        if not model_name:
            return "unknown"
        if model_name.startswith(("gpt-", "o1-", "o3-")):
            return "openai"
        if model_name.startswith("claude-"):
            return "anthropic"
        if model_name.startswith(("llama", "qwen", "mistral", "gemma")):
            return "ollama"
        return "unknown"

    def _extract_tokens(
        self, response: LLMResult, provider: str
    ) -> TokenUsage:
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage:
            usage = self._sum_generation_usage(response)
        return self._normalize_to_token_usage(usage, provider)

    def _sum_generation_usage(self, response: LLMResult) -> dict[str, Any]:
        """generation별 usage_metadata 합산 (Anthropic 등 ChatModel 케이스)."""
        merged: dict[str, int] = {}
        for gen_list in response.generations or []:
            for gen in gen_list:
                meta = getattr(gen, "generation_info", None) or {}
                usage = meta.get("usage_metadata") or meta.get("token_usage") or {}
                if hasattr(gen, "message") and gen.message is not None:
                    msg_meta = getattr(gen.message, "usage_metadata", None)
                    if msg_meta:
                        usage = msg_meta
                for k, v in (usage or {}).items():
                    if isinstance(v, int):
                        merged[k] = merged.get(k, 0) + v
        return merged

    def _normalize_to_token_usage(
        self, usage: dict[str, Any], provider: str
    ) -> TokenUsage:
        if not usage:
            return TokenUsage()
        if provider == "openai":
            prompt = int(usage.get("prompt_tokens", 0) or 0)
            completion = int(usage.get("completion_tokens", 0) or 0)
            total = int(
                usage.get("total_tokens", prompt + completion) or (prompt + completion)
            )
            return TokenUsage(prompt, completion, total)
        if provider == "anthropic":
            prompt = int(usage.get("input_tokens", 0) or 0)
            completion = int(usage.get("output_tokens", 0) or 0)
            return TokenUsage(prompt, completion, prompt + completion)
        if provider == "ollama":
            prompt = int(usage.get("prompt_eval_count", 0) or 0)
            completion = int(usage.get("eval_count", 0) or 0)
            return TokenUsage(prompt, completion, prompt + completion)
        # fallback: OpenAI 키
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(
            usage.get("total_tokens", prompt + completion) or (prompt + completion)
        )
        return TokenUsage(prompt, completion, total)
