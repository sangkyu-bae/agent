"""엔티티·관계 추출 프롬프트 (Design §2.2 적재).

타입 목록은 설정(DB) 데이터로 받는다 — 코어에 업무 용어를 하드코딩하지 않는다.
"""

from __future__ import annotations

_SYSTEM = (
    "당신은 사내 규정·업무 문서에서 지식 그래프를 만드는 추출기입니다.\n"
    "규칙:\n"
    "1. 문서에 실제로 나온 대상만 엔티티로 뽑습니다.\n"
    "   추측하거나 일반 상식을 더하지 않습니다.\n"
    "2. 엔티티 이름은 문서 표기를 그대로 씁니다.\n"
    "3. type 은 허용 목록 중 하나만 씁니다. 맞는 것이 없으면 '기타'를 씁니다.\n"
    "4. 관계의 source·target 은 반드시 entities 의 name 중 하나입니다.\n"
    "5. evidence 에는 관계를 보여 주는 원문 문장을 고치지 않고 그대로 옮깁니다.\n"
    "6. 조문 번호(제N조·별표·부칙)는 엔티티로 뽑지 않습니다(별도 규칙으로 처리).\n"
    "7. 뽑을 것이 없으면 빈 목록을 돌려줍니다."
)


def build_extraction_prompt(
    text: str, entity_types: tuple[str, ...], relation_types: tuple[str, ...]
) -> list[tuple[str, str]]:
    user = (
        f"허용 엔티티 타입: {', '.join(entity_types)}\n"
        f"허용 관계 타입: {', '.join(relation_types)}\n\n"
        f"[문서 조각]\n{text}"
    )
    return [("system", _SYSTEM), ("human", user)]
