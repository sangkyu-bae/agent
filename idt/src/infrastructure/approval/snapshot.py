"""SupervisorState 직렬화/복원 — 재개 스냅샷.

Design Ref: §3.1, §2.1 ④.

checkpointer 없이 재개가 가능한 이유: SupervisorState 는 평면 TypedDict 라
messages 만 LangChain 헬퍼로 변환하면 나머지는 순수 JSON 이다. LangGraph
체크포인터가 노드 경계마다 자동으로 하는 일을, 우리는 게이트 지점 한 곳에서
명시적으로 한다 — 대신 포맷을 직접 통제하고 버전을 붙일 수 있다.
"""
import json

from langchain_core.messages import messages_from_dict, messages_to_dict

from src.domain.approval.policies import ApprovalPolicy

_MESSAGES_KEY = "messages"
# 절단 시 본문을 잘라 남길 최소 길이 — 완전히 비우면 재개 맥락이 사라진다.
_MIN_CONTENT_CHARS = 200


class SnapshotSerializer:
    """SupervisorState ↔ JSON 문자열.

    `dumps_with_limit` 를 쓰면 상한(256KB) 초과 시 오래된 메시지부터 버린다.
    """

    SCHEMA_VERSION = 1

    @classmethod
    def is_supported(cls, version: int) -> bool:
        """포맷이 바뀐 스냅샷으로 재개하지 않기 위한 관문."""
        return version == cls.SCHEMA_VERSION

    @staticmethod
    def dumps(state: dict) -> str:
        payload = dict(state)
        payload[_MESSAGES_KEY] = messages_to_dict(state.get(_MESSAGES_KEY) or [])
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def loads(raw: str) -> dict:
        payload = json.loads(raw)
        payload[_MESSAGES_KEY] = messages_from_dict(payload.get(_MESSAGES_KEY) or [])
        return payload

    @classmethod
    def dumps_with_limit(cls, state: dict) -> tuple[str, bool]:
        """상한 이하로 직렬화한다. (payload, 절단여부) 반환.

        오래된 메시지부터 버리는 이유: 재개는 '지금 이어서' 하는 일이라
        최신 맥락이 더 가치 있다. 스칼라 필드는 항상 보존된다.
        """
        payload = cls.dumps(state)
        if not ApprovalPolicy.exceeds_snapshot_limit(payload.encode("utf-8")):
            return payload, False

        messages = list(state.get(_MESSAGES_KEY) or [])
        while len(messages) > 1:
            messages.pop(0)
            payload = cls.dumps({**state, _MESSAGES_KEY: messages})
            if not ApprovalPolicy.exceeds_snapshot_limit(payload.encode("utf-8")):
                return payload, True
        return cls._truncate_last(state, messages), True

    @classmethod
    def _truncate_last(cls, state: dict, messages: list) -> str:
        """남은 1건도 상한을 넘으면 본문 자체를 자른다.

        여기까지 오면 버릴 메시지가 없으므로, 재개 불가로 떨어뜨리는 대신
        앞부분만 남겨 맥락 일부라도 보존한다.
        """
        if not messages:
            return cls.dumps({**state, _MESSAGES_KEY: []})
        last = messages[-1]
        content = last.content if isinstance(last.content, str) else ""
        keep = max(_MIN_CONTENT_CHARS, len(content))
        while keep > _MIN_CONTENT_CHARS:
            keep //= 2
            last.content = content[:keep] + "…(생략됨)"
            payload = cls.dumps({**state, _MESSAGES_KEY: [last]})
            if not ApprovalPolicy.exceeds_snapshot_limit(payload.encode("utf-8")):
                return payload
        last.content = content[:_MIN_CONTENT_CHARS] + "…(생략됨)"
        return cls.dumps({**state, _MESSAGES_KEY: [last]})
