"""도구 선별 인프라 — LLM 호출과 프레임워크 어댑터.

Design Ref: §9.3 — 이 패키지의 코어(llm_tool_selector)는 langchain을 import 하지
않는다. LLM 인스턴스는 domain의 LLMFactoryInterface를 통해 받는다.
langchain 클래스 참조는 adapters/ 하위에만 존재한다
(infrastructure/../middleware_builder.py 가 세운 격리 선례를 따름).
"""
