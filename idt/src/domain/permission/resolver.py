"""PermissionResolver: role 권한 + user 추가 권한 → 최종 frozenset.

agent-user-context Design §3.3:
- 정책: 합집합 (현재). 향후 deny-list 추가 시 본 클래스에서 처리.
- 결과는 immutable (frozenset) — AuthContext에 안전하게 전달 가능.
"""


class PermissionResolver:
    """role permission + user-extra grant → 최종 frozenset.

    도메인 정책 — 외부 의존성 없음. 순수 함수.
    """

    @staticmethod
    def resolve(role_codes: list[str], user_codes: list[str]) -> frozenset[str]:
        return frozenset(role_codes) | frozenset(user_codes)
