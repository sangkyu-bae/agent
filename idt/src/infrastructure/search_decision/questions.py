"""search_decision 이 판정 백엔드에 묻는 질문 — 이 파일이 문구의 단일 출처.

Design Ref: judgment-backend D17 / Plan FR-13 — 질문은 소비 지점이 소유한다.
백엔드(Jev/AnyJev)가 바뀌어도 질문은 같다. 기존 `adapter._SYSTEM` 프롬프트의 판단
기준(엑셀 데이터만으로 충분하면 아니오, 애매하면 아니오 쪽)을 Noul 한 문장으로 옮겼다.
"""

QID = "needs_web_search"

SEARCH_DECISION_NOUL = (
    "state.question 은 사용자의 질문, state.analysis_text 는 엑셀 데이터만으로 작성한 "
    "분석 답변이다. 답변을 완성하려면 엑셀에 없는 최신 시세·뉴스·외부 통계 같은 정보가 "
    "추가로 필요한가? 엑셀 데이터만으로 충분히 답했으면 아니오."
)
