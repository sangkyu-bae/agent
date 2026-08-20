"""에이전트 생성용 의도 축 프리셋 (Design §4.5 / Plan FR-13).

"데이터 분석해주는 에이전트 만들어줘" 같은 한 문장에서, 초안 품질을 실제로 가르는
정보는 **무슨 일을 / 어떤 범위로 / 어떤 데이터로 / 어떤 형태로 / 어떤 어조로** 다.
이 5축을 데이터로 선언해 두면 되묻기가 LLM 의 재량이 아니라 축의 미충족에서
나오므로, 같은 요청에 같은 질문이 나온다.

**여기 있는 이유** (Plan D2): `domain/intent` 는 축의 *의미* 를 몰라야 한다.
"어조"·"데이터소스" 같은 도메인 어휘가 코어에 침투하면 선행 사이클 D3
("분류 체계는 호출자 주입")가 무너지고, 모듈이 에이전트 생성 전용이 된다.
그래서 축은 호출자 쪽인 여기에 두고 주입만 한다.

**이번 사이클엔 소비자가 없다** (Plan D8 / R6). 1차 배선 지점은 `planner.py`
(`AgentPlanner.plan`)이며, 진입 조건 2개는 Design §11.4 참조.
"""
from src.domain.intent.schemas import SlotSpec

# required 배분 근거 (Design §4.5): 앞 3축은 없으면 도구·프롬프트가 결정 불가라
# 초안 자체를 만들 수 없다. 뒤 2축은 합리적 기본값이 있으므로 되묻기 예산
# (라운드 2 × 질문 3)을 앞 3축에 몰아준다.
#
# options 는 **고정 목록이 아니라 LLM 앵커링용 예시**다 (Plan D3 / R4).
# 어댑터가 "(예: ...)" 로 렌더하고 "예시를 무시하고 새로 만드세요"를 함께 지시한다.
AGENT_BUILD_SLOTS: list[SlotSpec] = [
    SlotSpec(
        key="task",
        description="이 에이전트가 사용자를 위해 해 줄 일",
        options=["데이터 분석", "문서 질의응답", "보고서 작성", "정보 검색"],
        required=True,
    ),
    SlotSpec(
        key="domain_detail",
        description="그 일을 구체적으로 어떤 범위·방식으로 하는지",
        options=["요약 통계", "추세 분석", "이상 탐지", "비교 분석"],
        required=True,
    ),
    SlotSpec(
        key="data_source",
        description="에이전트가 다룰 데이터가 어디에 있는지",
        options=["엑셀/CSV 업로드", "지식베이스(KB)", "웹 검색", "DB 연결"],
        required=True,
    ),
    SlotSpec(
        key="output_format",
        description="결과를 어떤 형태로 받고 싶은지",
        options=["텍스트 요약", "표", "차트", "다운로드 파일"],
        required=False,
    ),
    SlotSpec(
        key="tone",
        description="답변할 때의 어조와 대상 독자",
        options=["간결한 실무형", "친근한 설명형", "격식 있는 보고형"],
        required=False,
    ),
]
