"""ChunkingProfilePolicy — 프로파일 이름/규칙/사이즈 검증 (clause-aware-chunking Design §5.2, D12).

domain 레이어 규칙 준수: 표준 라이브러리 `re`만 사용, 외부 의존 없음.
정규식 컴파일 검증 + 패턴 길이/개수 상한으로 ReDoS 노출을 최소화한다 (NFR-07).
"""
import re

from src.domain.chunking_profile.entities import (
    CHILD_LEVEL,
    PARENT_LEVEL,
    BoundaryRule,
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_VALID_LEVELS = {PARENT_LEVEL, CHILD_LEVEL}


class ChunkingProfilePolicy:
    MAX_NAME_LENGTH = 100
    MAX_PATTERN_LENGTH = 200
    MAX_RULES = 50
    PARENT_SIZE_MIN = 100
    PARENT_SIZE_MAX = 8000
    CHILD_SIZE_MIN = 100
    CHILD_SIZE_MAX = 4000
    OVERLAP_MIN = 0
    OVERLAP_MAX = 500

    @staticmethod
    def validate_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Chunking profile name must not be empty")
        if len(cleaned) > ChunkingProfilePolicy.MAX_NAME_LENGTH:
            raise ValueError(
                f"Chunking profile name max "
                f"{ChunkingProfilePolicy.MAX_NAME_LENGTH} chars"
            )
        if _CONTROL_CHARS.search(cleaned):
            raise ValueError(
                "Chunking profile name must not contain control characters"
            )
        return cleaned

    @classmethod
    def validate_rules(cls, rules: list[BoundaryRule]) -> None:
        if not rules:
            raise ValueError("At least one boundary rule is required")
        if len(rules) > cls.MAX_RULES:
            raise ValueError(f"boundary_rules max {cls.MAX_RULES} entries")
        parent_count = 0
        for rule in rules:
            cls._validate_rule(rule)
            if rule.level == PARENT_LEVEL:
                parent_count += 1
        if parent_count < 1:
            raise ValueError("At least one 'parent' level rule is required")

    @classmethod
    def _validate_rule(cls, rule: BoundaryRule) -> None:
        if rule.level not in _VALID_LEVELS:
            raise ValueError(
                f"rule level must be 'parent' or 'child', got '{rule.level}'"
            )
        if not rule.pattern or not rule.pattern.strip():
            raise ValueError("rule pattern must not be empty")
        if len(rule.pattern) > cls.MAX_PATTERN_LENGTH:
            raise ValueError(
                f"rule pattern max {cls.MAX_PATTERN_LENGTH} chars"
            )
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex pattern '{rule.pattern}': {exc}")

    @classmethod
    def validate_sizes(
        cls, parent_chunk_size: int, chunk_size: int, chunk_overlap: int
    ) -> None:
        if not (cls.PARENT_SIZE_MIN <= parent_chunk_size <= cls.PARENT_SIZE_MAX):
            raise ValueError(
                f"parent_chunk_size must be "
                f"{cls.PARENT_SIZE_MIN}~{cls.PARENT_SIZE_MAX}"
            )
        if not (cls.CHILD_SIZE_MIN <= chunk_size <= cls.CHILD_SIZE_MAX):
            raise ValueError(
                f"chunk_size must be {cls.CHILD_SIZE_MIN}~{cls.CHILD_SIZE_MAX}"
            )
        if not (cls.OVERLAP_MIN <= chunk_overlap <= cls.OVERLAP_MAX):
            raise ValueError(
                f"chunk_overlap must be {cls.OVERLAP_MIN}~{cls.OVERLAP_MAX}"
            )
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if chunk_size > parent_chunk_size:
            raise ValueError("chunk_size must not exceed parent_chunk_size")

    @classmethod
    def validate_kb_override(
        cls, chunk_size: int | None, chunk_overlap: int | None
    ) -> None:
        """KB 오버라이드 검증 (Design D7): overlap 지정 시 size 필수 + 범위."""
        if chunk_overlap is not None and chunk_size is None:
            raise ValueError(
                "chunk_size is required when chunk_overlap is set"
            )
        if chunk_size is not None:
            if not (cls.CHILD_SIZE_MIN <= chunk_size <= cls.CHILD_SIZE_MAX):
                raise ValueError(
                    f"chunk_size must be "
                    f"{cls.CHILD_SIZE_MIN}~{cls.CHILD_SIZE_MAX}"
                )
        if chunk_overlap is not None:
            if not (cls.OVERLAP_MIN <= chunk_overlap <= cls.OVERLAP_MAX):
                raise ValueError(
                    f"chunk_overlap must be "
                    f"{cls.OVERLAP_MIN}~{cls.OVERLAP_MAX}"
                )
            if chunk_size is not None and chunk_overlap >= chunk_size:
                raise ValueError("chunk_overlap must be less than chunk_size")

    @staticmethod
    def can_delete(profile) -> None:
        """기본 프로파일은 삭제 불가 (Design D3)."""
        if profile.is_default:
            raise ValueError("default profile cannot be deleted")
