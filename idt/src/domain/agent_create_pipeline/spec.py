"""에이전트 생성용 intent 스펙 — 서버 소유 (Design §3.2 / Plan D5).

"하나의 엔드포인트"가 성립하려면 호출자가 분류 스펙을 몰라야 한다. 그래서
스펙을 여기(domain 상수)에 두되, intent 모듈의 무결합 설계는 그대로 유지한다 —
스펙은 여전히 AnalyzeIntentUseCase 의 주입 인자다.

슬롯만 있는 형태(labels 없음)를 쓴다: 목적은 분류가 아니라 정보 수집이며,
IntentSpec 이 이 형태를 "에이전트 생성이 쓰는 형태"로 예정해 두었다.
required 는 purpose 하나뿐이다 — required 축이 늘수록 되묻기 왕복이 길어져
단일 엔드포인트의 가치가 줄기 때문이다.

domain 은 env 를 읽지 않는다 — SlotLimits 오버라이드는 config 가 조립 시 주입.
"""
from src.domain.intent.schemas import IntentSpec, SlotSpec

PURPOSE_SLOT_KEY = "purpose"


def build_agent_create_spec() -> IntentSpec:
    """매 호출 새 인스턴스를 만든다 — 호출자 간 스펙 오염 방지."""
    return IntentSpec(
        labels=[],
        slots=[
            SlotSpec(
                key=PURPOSE_SLOT_KEY,
                description="이 에이전트가 해결할 핵심 업무나 목적",
                required=True,
            ),
            SlotSpec(
                key="target_users",
                description="누가 사용하는 에이전트인지",
                options=["팀 내부", "전사 공용", "고객 응대"],
            ),
            SlotSpec(
                key="data_sources",
                description="에이전트가 참조할 자료·지식 출처",
                options=["사내 문서", "웹 검색", "데이터베이스"],
            ),
            SlotSpec(
                key="tone",
                description="응답 말투와 형식",
                options=["격식체", "간결한 요약", "상세한 설명"],
            ),
            # prompt-depth §3.5 — 신규 2축. "LLM 이 목적만 알면 추론할 수 있는
            # 것"은 묻지 않는다(책임·절차·예시). 반대로 아래 둘은 사용자만 알며,
            # LLM 이 추측하면 위험한 축이라 프롬프트의 context/principles 섹션의
            # 근거가 된다 (FR-19).
            #
            # 둘 다 optional 이다 (FR-16): required 로 올리면 "간단한 봇 하나"에도
            # 되묻기를 강요해 단일 엔드포인트의 가치가 줄어든다.
            SlotSpec(
                key="constraints",
                description="반드시 지켜야 할 규칙이나 하지 말아야 할 것",
                options=["출처 명시 필수", "추측 금지", "개인정보 미출력"],
            ),
            SlotSpec(
                key="decision_priority",
                description="판단이 충돌할 때 무엇을 우선할지",
                options=["정확성 우선", "속도 우선", "안전성 우선"],
            ),
        ],
    )
