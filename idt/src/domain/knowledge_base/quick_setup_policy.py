"""KbQuickSetupPolicy — 빌더 원스톱 KB 구성의 명명·범위 규칙.

agent-kb-quick-setup Design §3.1.

Design Ref: §9.4 — 컬렉션 이름은 kb_id 앞 8자, KB 범위는 에이전트 공개 범위를 따른다.
"""
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.policy import KnowledgeBasePolicy

_VISIBILITY_TO_SCOPE: dict[str, CollectionScope] = {
    "private": CollectionScope.PERSONAL,
    "department": CollectionScope.DEPARTMENT,
    "public": CollectionScope.PUBLIC,
}


class KbQuickSetupPolicy:
    COLLECTION_PREFIX = "kb-"
    COLLECTION_ID_CHARS = 8
    MAX_FILES = 10
    NAME_SUFFIX_MAX = 20
    # KB 업로드 모달 accept 와 동일 (kb-screens 위키 v2).
    # 새 포맷 추가 시 백엔드 파서 라우팅 + 여기.
    ALLOWED_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".hwp", ".hwpx")

    @staticmethod
    def collection_name_for(kb_id: str) -> str:
        if not kb_id:
            raise ValueError("kb_id is required to derive a collection name")
        return (
            f"{KbQuickSetupPolicy.COLLECTION_PREFIX}"
            f"{kb_id[: KbQuickSetupPolicy.COLLECTION_ID_CHARS]}"
        )

    @staticmethod
    def is_auto_collection(name: str) -> bool:
        return name.startswith(KbQuickSetupPolicy.COLLECTION_PREFIX)

    @staticmethod
    def scope_for_visibility(visibility: str) -> CollectionScope:
        try:
            return _VISIBILITY_TO_SCOPE[visibility]
        except KeyError:
            raise ValueError(f"Unknown visibility: '{visibility}'") from None

    @staticmethod
    def validate_files(filenames: list[str]) -> None:
        """개수 1~MAX_FILES, 확장자 화이트리스트. 위반은 ValueError(422)."""
        if not filenames:
            raise ValueError("At least one file is required")
        if len(filenames) > KbQuickSetupPolicy.MAX_FILES:
            raise ValueError(
                f"Too many files: {len(filenames)} (max {KbQuickSetupPolicy.MAX_FILES})"
            )
        for name in filenames:
            ext = name[name.rfind(".") :].lower() if "." in name else ""
            if ext not in KbQuickSetupPolicy.ALLOWED_EXTENSIONS:
                raise ValueError(f"Unsupported file extension: '{ext}' ({name})")

    @staticmethod
    def next_name(base: str, attempt: int) -> str:
        """중복 회피 이름. attempt 0 → base, n → "base (n+1)".

        상한 초과는 ValueError.
        """
        if attempt >= KbQuickSetupPolicy.NAME_SUFFIX_MAX:
            raise ValueError(
                f"Too many knowledge bases named '{base}' "
                f"(limit {KbQuickSetupPolicy.NAME_SUFFIX_MAX})"
            )
        if attempt == 0:
            return base
        suffix = f" ({attempt + 1})"
        room = KnowledgeBasePolicy.MAX_NAME_LENGTH - len(suffix)
        return f"{base[:room].rstrip()}{suffix}"
