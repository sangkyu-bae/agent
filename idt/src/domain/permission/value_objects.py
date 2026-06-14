"""PermissionCode enum + 한국어 라벨.

agent-user-context Design §3.2:
- 권한 코드의 단일 진실 공급원 (Single Source of Truth)
- 변경 시 DB seed(V029)와 동기화 필요
- LLM 노출 시 label_ko로 변환 (render_user_context_block에서 사용)
"""
from enum import Enum


class PermissionCode(str, Enum):
    """사내 권한 코드. str 상속 → frozenset(str)과 직접 비교 가능."""

    READ_PUBLIC_DOCS = "READ_PUBLIC_DOCS"
    READ_INTERNAL_NOTICES = "READ_INTERNAL_NOTICES"
    READ_DEPARTMENT_DOCS = "READ_DEPARTMENT_DOCS"
    USE_RAG_SEARCH = "USE_RAG_SEARCH"
    USE_WEB_SEARCH = "USE_WEB_SEARCH"
    CREATE_AGENT = "CREATE_AGENT"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"

    @property
    def label_ko(self) -> str:
        """LLM 프롬프트 노출용 한국어 라벨."""
        return _LABELS_KO[self]


_LABELS_KO: dict[PermissionCode, str] = {
    PermissionCode.READ_PUBLIC_DOCS:      "사내 공개 문서 조회",
    PermissionCode.READ_INTERNAL_NOTICES: "내부 공지 조회",
    PermissionCode.READ_DEPARTMENT_DOCS:  "소속 부서 문서 조회",
    PermissionCode.USE_RAG_SEARCH:        "RAG 문서 검색",
    PermissionCode.USE_WEB_SEARCH:        "웹 검색",
    PermissionCode.CREATE_AGENT:          "에이전트 생성",
    PermissionCode.MANAGE_USERS:          "사용자 관리",
    PermissionCode.MANAGE_PERMISSIONS:    "권한 관리",
}
