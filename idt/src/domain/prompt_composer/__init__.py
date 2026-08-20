"""prompt_composer 도메인 — 시스템 프롬프트 생성의 순수 규칙.

Design Ref: docs/02-design/features/prompt-composer.design.md §9.1
이 패키지는 langchain·sqlalchemy·fastapi·pydantic 을 import 하지 않으며,
agent_composer 패키지에도 의존하지 않는다 (Design D1 / Q3).
"""
