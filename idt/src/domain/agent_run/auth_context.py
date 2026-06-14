"""AuthContext — Agent 런타임 사용자 컨텍스트 ValueObject.

agent-user-context Design §3.1:
- frozen=True (immutable) — 요청 시작 시 1회 조립 후 변경 금지
- 권한 검증의 단일 진실 공급원 (Single Source of Truth)
- LLM 노출 시 render_user_context_block 헬퍼를 거쳐 whitelist 필드만 통과
- RunContext(관측성 전용)와 별도의 ContextVar로 관리 — 책임 분리

⚠️ 절대 금지:
- employee_no, email, password_hash 등 민감 필드를 추가하지 말 것
- mutable container(list/dict/set) 필드 추가 금지 — tuple/frozenset만 사용
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    display_name: str
    role: str                              # "user" | "admin" | "anonymous"
    primary_department_id: str | None      # is_primary=True인 부서 1개
    primary_department_name: str | None
    department_ids: tuple[str, ...]        # 사용자가 속한 모든 부서 ID
    department_names: tuple[str, ...]      # 사용자가 속한 모든 부서명 (display 용)
    permissions: frozenset[str]            # 최종 권한 코드 집합 (role + user grants)
    tenant_id: str | None = None           # 향후 멀티테넌트 슬롯 — 현재 None

    @staticmethod
    def public_anonymous() -> "AuthContext":
        """auth_ctx 누락/스크립트 호출 시 안전 디폴트 (Fail-Closed).

        - permissions = frozenset() — 어떤 권한도 없음
        - LLM prepend 블록은 빈 문자열로 처리됨 (render_user_context_block 측)
        - Tool/Repository는 공용 데이터만 노출 (USE_RAG_SEARCH 없으므로 거부)
        """
        return AuthContext(
            user_id=0,
            display_name="(미인증 사용자)",
            role="anonymous",
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
            permissions=frozenset(),
        )

    def has(self, code: str) -> bool:
        """권한 코드 존재 여부 — 모든 권한 체크의 단일 진입점.

        Tool/Repository에서 이 메서드만 사용하면, 향후 deny-list나
        시간 기반 권한이 추가되어도 단일 위치만 수정하면 된다.
        """
        return code in self.permissions
