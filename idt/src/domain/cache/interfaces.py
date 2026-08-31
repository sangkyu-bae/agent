"""CachePort: 범용 KV 캐시 포트.

Design Ref: admin-default-llm-routing §4.1 / DR-1 / DR-2 / DR-7.

포트를 먼저 뚫어두는 이유는 나중에 Redis 등 프로세스 외부 저장소로 교체할 때
소비자 코드를 건드리지 않기 위함이다 (SelectionCachePort 선례와 동일 취지).
"""
from abc import ABC, abstractmethod
from typing import Any


class CachePort(ABC):
    """범용 KV 캐시.

    계약
    ----
    1. **value 는 JSON 직렬화 가능해야 한다.**
       Redis 등 프로세스 외부 저장소로 교체될 수 있으므로, 소켓·클라이언트
       핸들을 가진 객체(예: LangChain ``BaseChatModel``)를 담아서는 안 된다.
       그런 객체는 프로세스 로컬 캐시에 따로 격리한다 (Design DR-1).

    2. **값 의미론(value semantics)을 갖는다.**
       저장하거나 조회한 값을 호출자가 변경해도 캐시 내용은 영향받지 않는다.
       Redis 어댑터는 직렬화 사본을 다루므로, 인메모리 구현이 참조를 공유하면
       구현 교체 시 동작이 달라진다 (Design G2).

    3. **구현체는 예외를 던지지 않는다.**
       조회 실패는 miss(``None``), 저장·삭제 실패는 무시로 취급한다.
       캐시는 부가 기능이며 장애가 요청을 실패시켜서는 안 된다 (Design DR-7).

    키 규약
    ------
    ``<도메인>:<식별자>`` — 예: ``llm_model:default``, ``llm_model:name:gpt-4o``.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """캐시 값을 반환한다. 미스·만료·오류면 ``None``."""

    @abstractmethod
    async def set(
        self, key: str, value: Any, ttl_seconds: float | None = None
    ) -> None:
        """값을 저장한다.

        Args:
            key: 캐시 키 (``<도메인>:<식별자>``).
            value: JSON 직렬화 가능한 값.
            ttl_seconds: 만료 시간(초). ``None`` 이면 구현체 기본 TTL을 따른다.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """단건 삭제. 존재하지 않는 키여도 오류가 아니다."""

    @abstractmethod
    async def clear(self) -> None:
        """전체 비움."""
