"""AgentRun 도메인: Run/Step/Tool/Retrieval/LlmCall 관측성 영속화.

AGENT-OBS-001: 운영팀이 "어떤 답변을 어떤 LLM·툴·근거로 만들었는지"를
LangSmith 외부 SaaS 의존 없이 우리 DB(SSoT)에서 추적할 수 있게 한다.

레이어 규칙: 외부 의존성(SQLAlchemy/LangChain/asyncio) 사용 금지.
값 타입(dataclass + Enum + Decimal)과 정책(policy) 함수만 정의한다.
"""
