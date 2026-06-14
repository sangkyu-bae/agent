"""LangChain message content 정규화 (domain 순수 함수).

FIX-CHAT-REASONING-OBJECT-RENDER Plan §4-1.

LangChain `BaseMessage.content` / streaming chunk.content 는 모델·구성에 따라
`str` 또는 content block 리스트(`[{"type": "text", "text": "..."}, ...]`)로 내려온다.
WS 토큰 payload 는 항상 문자열이어야 하므로(프론트가 문자열 결합으로 누적),
이 함수로 평탄화된 문자열을 보장한다. 비-텍스트 block(tool_use 등)은 무시한다.
외부 의존 없는 순수 함수이므로 domain 레이어에 둔다.
"""
from __future__ import annotations


def coerce_message_text(content: object) -> str:
    """message content(str | list[block] | None) → 평탄화 문자열.

    - str: 그대로 반환
    - list: text block(dict의 "text" 문자열) 또는 str 요소만 이어붙임
    - 그 외(None, 숫자 등): 빈 문자열
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""
