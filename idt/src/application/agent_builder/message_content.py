"""상태 메시지 content 접근 단일 지점 — chat-image-attachment Design §9.4 / D-02.

상태(`SupervisorState.messages`)의 content 는 `str | list[block]` 이다
(이미지 첨부 턴의 사용자 메시지는 `[{"type":"text"}, <image block>...]`).
agent_builder·agent_run 에서 content 를 문자열로 다루는 모든 지점은 이 모듈을
거친다 — 계약 테스트(test_message_content_contract.py)가 직접 접근을 금지한다.

- message_text(): 텍스트 블록만 이어붙인 문자열 (이미지 블록은 기본 제외)
- is_multimodal() / image_blocks(): 이미지 블록 유무·추출 (서브에이전트 전달용)
- redact_image_blocks(): 로그·실행 이력 직렬화용 — base64 를 마커로 치환
벤더 포맷(OpenAI image_url / Anthropic image)은 여기서 "판별"만 하고 생성하지 않는다.
"""
from __future__ import annotations

from typing import Any

from src.domain.llm.message_content import coerce_message_text

_IMAGE_BLOCK_TYPES = frozenset({"image_url", "image"})


def _raw_content(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("content", "")
    if hasattr(msg, "content"):
        return msg.content
    return msg


def _is_image_block(block: Any) -> bool:
    return isinstance(block, dict) and block.get("type") in _IMAGE_BLOCK_TYPES


def _image_mime(block: dict) -> str:
    if block.get("type") == "image":
        return str((block.get("source") or {}).get("media_type", "image"))
    url = str((block.get("image_url") or {}).get("url", ""))
    if url.startswith("data:") and ";" in url:
        return url[5:].split(";", 1)[0]
    return "image"


def _marker(block: dict) -> str:
    return f"[image:{_image_mime(block)}]"


def message_text(msg: Any, *, keep_image_markers: bool = False) -> str:
    """메시지(dict | BaseMessage | 원시값) → 텍스트. 이미지 블록은 제외(옵션: 마커)."""
    content = _raw_content(msg)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    if not keep_image_markers:
        return coerce_message_text(content)
    parts = [
        _marker(b) if _is_image_block(b) else coerce_message_text([b])
        for b in content
    ]
    return "\n".join(p for p in parts if p)


def is_multimodal(msg: Any) -> bool:
    content = _raw_content(msg)
    return isinstance(content, list) and any(_is_image_block(b) for b in content)


def image_blocks(msg: Any) -> list[dict]:
    content = _raw_content(msg)
    if not isinstance(content, list):
        return []
    return [b for b in content if _is_image_block(b)]


def redact_messages(messages: list) -> list:
    """messages 복사본 — 각 content 의 이미지 블록을 마커로 치환 (저장·로그 직렬화용).

    chat-image-attachment Analysis G-C1: 승인 게이트 재개 스냅샷(approval_request)에
    base64 가 남지 않게 한다. BaseMessage 는 model_copy, dict 는 얕은 복사.
    """
    out = []
    for m in messages or []:
        content = _raw_content(m)
        if not (isinstance(content, list) and any(_is_image_block(b) for b in content)):
            out.append(m)
            continue
        redacted = redact_image_blocks(content)
        if isinstance(m, dict):
            out.append({**m, "content": redacted})
        elif hasattr(m, "model_copy"):
            out.append(m.model_copy(update={"content": redacted}))
        else:
            out.append(m)
    return out


def redact_image_blocks(content: Any) -> Any:
    """content 의 이미지 블록을 텍스트 마커 블록으로 치환한 복사본 (str 은 그대로)."""
    if not isinstance(content, list):
        return content
    return [
        {"type": "text", "text": _marker(b)} if _is_image_block(b) else b
        for b in content
    ]
