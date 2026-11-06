"""PiiMessageMasker: LangChain 메시지 단위 마스킹/원복.

Design Ref: pii-masking-integration §4.2 — 미들웨어와 GuardedLlm 프록시가 공유하는
코어. 원본 메시지는 바꾸지 않고 변경이 있을 때만 사본을 만든다. 그래프 상태에는
원본이 남고, 외부 LLM으로 나가는 요청에만 placeholder가 들어간다 (FR-02).

content는 text 블록만 다룬다. 이미지 블록의 base64 문자열에 범용 변환을 쓰면
숫자열이 PII 패턴에 걸려 이미지가 깨진다 (FR-16).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from pydantic import BaseModel

from src.application.pii_masking.pii_masking_service import PiiMaskingService
from src.application.pii_masking.stream_restorer import PlaceholderStreamRestorer
from src.domain.pii_masking.interfaces import PiiInspectPort
from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE
from src.domain.pii_masking.schemas import PiiMaskingMode, PiiRunScope

_TextFn = Callable[[str], str]


def _map_content(content: object, fn: _TextFn) -> object:
    """메시지 content의 텍스트만 변환. 이미지 등 다른 블록은 그대로 둔다."""
    if isinstance(content, str):
        return fn(content)
    if not isinstance(content, list):
        return content
    mapped: list = []
    for block in content:
        if isinstance(block, str):
            mapped.append(fn(block))
        elif isinstance(block, dict) and block.get("type") == "text":
            mapped.append({**block, "text": fn(block.get("text", ""))})
        else:
            mapped.append(block)
    return mapped


def _map_value(value: object, fn: _TextFn) -> object:
    """tool_calls 인자·additional_kwargs·구조화 출력의 문자열을 재귀 변환."""
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {key: _map_value(item, fn) for key, item in value.items()}
    if isinstance(value, list):
        return [_map_value(item, fn) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_value(item, fn) for item in value)
    if isinstance(value, BaseModel):
        return _map_model(value, fn)
    return value


def _map_model(model: BaseModel, fn: _TextFn) -> BaseModel:
    updates = {}
    for name in type(model).model_fields:
        current = getattr(model, name)
        mapped = _map_value(current, fn)
        if mapped != current:
            updates[name] = mapped
    return model.model_copy(update=updates) if updates else model


def _content_strings(content: object) -> Iterator[str]:
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                yield block
            elif isinstance(block, dict) and block.get("type") == "text":
                yield str(block.get("text", ""))


class PiiMessageMasker:
    """메시지·구조화 출력을 scope의 vault 기준으로 변환한다."""

    def __init__(self, service: PiiMaskingService) -> None:
        self._service = service

    def new_scope(self) -> PiiRunScope:
        return self._service.new_scope()

    @property
    def inspector(self) -> PiiInspectPort:
        """MCP 경계 검사기 (Design §4.6). 같은 서비스·같은 활성 타입을 쓴다."""
        return self._service

    def mask_messages(
        self, messages: list[BaseMessage], scope: PiiRunScope
    ) -> list[BaseMessage]:
        """전체 메시지의 placeholder 형태 문자열을 먼저 예약한 뒤 마스킹한다."""
        for message in messages:
            for text in _content_strings(message.content):
                scope.vault.reserve_literals(text)
        return [self.mask_message(message, scope) for message in messages]

    def mask_request(
        self,
        messages: list[BaseMessage],
        scope: PiiRunScope,
        system: BaseMessage | None = None,
    ) -> tuple[list[BaseMessage], BaseMessage | None]:
        """system 포함 요청 1건을 마스킹한다 (Check G-13).

        placeholder 가 실제로 나갔으면 system 끝에 안내를 붙인다. system 이 없으면
        안내만 담은 SystemMessage 를 만든다.
        """
        batch = ([system] if system is not None else []) + list(messages)
        masked = self.mask_messages(batch, scope)
        head = masked[0] if system is not None else None
        body = masked[1:] if system is not None else masked
        if not self._sent_known_placeholder(masked, scope):
            return body, head
        return body, _with_notice(head)

    @staticmethod
    def _sent_known_placeholder(
        messages: list[BaseMessage], scope: PiiRunScope
    ) -> bool:
        """vault 가 아는 placeholder 가 하나라도 나가는가. shadow 는 원문이라 False."""
        return any(
            scope.vault.restore(text) != text
            for message in messages
            for text in _content_strings(message.content)
        ) and scope.mode is PiiMaskingMode.ON

    def mask_message(self, message: BaseMessage, scope: PiiRunScope) -> BaseMessage:
        def mask(text: str) -> str:
            return self._service.mask_text(text, scope)

        return self._transform(message, content_fn=mask, args_fn=mask)

    def restore_message(self, message: BaseMessage, scope: PiiRunScope) -> BaseMessage:
        """본문은 고아까지 처리하고, 도구 인자는 알려진 placeholder만 원복한다."""
        return self._transform(
            message,
            content_fn=lambda text: self._service.restore_text(text, scope),
            args_fn=lambda text: self._service.restore_known_text(text, scope),
        )

    def restore_output(self, output: object, scope: PiiRunScope) -> object:
        """AIMessage, BaseModel, dict(include_raw), str 등 모델 출력을 원복한다.

        Design D-08: 메시지가 아닌 구조화 출력은 알려진 placeholder만 원복하고 고아는
        남긴다. 파이프라인이 구조화 출력을 그대로 도구 인자로 쓰기 때문에, redact하면
        `[REDACTED_EMAIL]`로 도구가 실행된다. 고아는 도구 경계(MCP 어댑터·집행기)가
        막는다.
        """
        if isinstance(output, BaseMessage):
            return self.restore_message(output, scope)
        if isinstance(output, dict):
            return {
                key: self.restore_output(item, scope) for key, item in output.items()
            }
        return _map_value(
            output, lambda text: self._service.restore_known_text(text, scope)
        )

    def has_orphan(self, value: object, scope: PiiRunScope) -> bool:
        return self._service.has_orphan(value, scope)

    def new_stream_restorer(self, scope: PiiRunScope) -> PlaceholderStreamRestorer:
        """런 1개의 토큰 원복기 (Design §4.5). 호출자는 서비스를 몰라도 된다."""
        return PlaceholderStreamRestorer(self._service, scope)

    @staticmethod
    def _transform(
        message: BaseMessage, *, content_fn: _TextFn, args_fn: _TextFn
    ) -> BaseMessage:
        """변경된 필드만 사본에 반영한다. 변경이 없으면 원본 객체를 돌려준다.

        additional_kwargs는 원문 tool_calls(JSON 인자)를 담으므로 인자 규칙을 쓴다.
        """
        updates: dict[str, object] = {}
        content = _map_content(message.content, content_fn)
        if content != message.content:
            updates["content"] = content
        extra = _map_value(message.additional_kwargs, args_fn)
        if extra != message.additional_kwargs:
            updates["additional_kwargs"] = extra
        if isinstance(message, AIMessage):
            updates.update(_transform_tool_calls(message, args_fn))
        return message.model_copy(update=updates) if updates else message


def _with_notice(system: BaseMessage | None) -> BaseMessage:
    """system 본문 끝에 안내를 붙인 사본. 블록 content 는 text 블록을 덧붙인다."""
    if system is None:
        return SystemMessage(content=PII_PLACEHOLDER_NOTICE)
    content = system.content
    if isinstance(content, list):
        added: object = [*content, {"type": "text", "text": PII_PLACEHOLDER_NOTICE}]
    else:
        added = f"{content}\n\n{PII_PLACEHOLDER_NOTICE}" if content else (
            PII_PLACEHOLDER_NOTICE
        )
    return system.model_copy(update={"content": added})


def _transform_tool_calls(message: AIMessage, fn: _TextFn) -> dict[str, object]:
    updates: dict[str, object] = {}
    calls = [
        {**call, "args": _map_value(call["args"], fn)} for call in message.tool_calls
    ]
    if calls != message.tool_calls:
        updates["tool_calls"] = calls
    invalid = [
        {**call, "args": _map_value(call.get("args"), fn)}
        for call in message.invalid_tool_calls
    ]
    if invalid != message.invalid_tool_calls:
        updates["invalid_tool_calls"] = invalid
    return updates
