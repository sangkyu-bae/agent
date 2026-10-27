"""OpenerPolicy: 에이전트 오프너(대화 시작 예시 질문) 도메인 규칙.

Design Ref: agent-opener §3.1 — 검증 SoT는 이 클래스 한 곳.
개수·길이 상한은 API 스키마(Pydantic)가 먼저 422로 막고, 여기서는 strip 정규화 +
빈 항목·중복 거부 + 상한 재검증(2차 방어 — 포크·직접 호출 경로)을 맡는다.

⚠️ 예외 메시지에 '최대'·'이미'·'찾을 수 없' 문자열 금지 (Design §6.3):
agent_builder_router 의 ValueError 매퍼가 이 단어로 409/404 를 만든다.
"""


class OpenerPolicy:
    MAX_COUNT = 12
    MAX_LENGTH = 200

    @classmethod
    def normalize(cls, texts: list[str]) -> list[str]:
        """strip → 빈 항목 거부 → 길이·중복 거부 → 개수 거부. 순서 보존."""
        if len(texts) > cls.MAX_COUNT:
            raise ValueError(
                f"오프너는 {cls.MAX_COUNT}개까지 등록할 수 있습니다. "
                f"(입력 {len(texts)}개)"
            )
        result: list[str] = []
        seen: set[str] = set()
        for position, raw in enumerate(texts, start=1):
            text = raw.strip()
            if not text:
                raise ValueError(f"오프너 {position}번째 항목이 비어 있습니다")
            if len(text) > cls.MAX_LENGTH:
                raise ValueError(
                    f"오프너 {position}번째 항목은 {cls.MAX_LENGTH}자 이하여야 합니다"
                )
            if text in seen:
                # Check G1: 사용자 텍스트를 메시지에 넣으면 '최대' 등이 섞여
                # 라우터 매퍼가 409/404 로 바꾼다 — 위치 번호만 쓴다.
                raise ValueError(f"오프너 {position}번째 항목이 앞의 항목과 중복됩니다")
            seen.add(text)
            result.append(text)
        return result
