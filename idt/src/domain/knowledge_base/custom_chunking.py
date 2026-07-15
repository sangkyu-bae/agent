"""KB 커스텀 청킹 설정 (kb-custom-chunking Design §4, D1~D5).

전략 5종 + 토큰 파라미터 + 경계 정규식을 KB JSON 컬럼(custom_chunking_config)에
보관하기 위한 스키마와 검증 policy. 수치 상한은 ChunkingProfilePolicy 상수를
재사용한다 (D5, D11). domain 규칙 준수: pydantic/표준 re만 사용.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from src.domain.chunking_profile.policy import ChunkingProfilePolicy

STRATEGY_BOUNDARY_PATTERN = "boundary_pattern"

# 사용자 노출 전략명 → ChunkingStrategyFactory 전략명 (D3)
_FACTORY_STRATEGY = {
    "full_token": "full_token",
    "parent_child": "parent_child",
    "semantic": "semantic",
    "section_aware": "section_aware",
    STRATEGY_BOUNDARY_PATTERN: "clause_aware",
}


class CustomBoundaryRule(BaseModel):
    """경계 규칙 하나 — 정규식 패턴 + 우선순위 + 계층 (Design §4.1)."""

    pattern: str
    priority: int
    level: Literal["parent", "child"]


class CustomChunkingConfig(BaseModel):
    version: Literal[1] = 1
    strategy: Literal[
        "full_token", "parent_child", "semantic",
        "section_aware", "boundary_pattern",
    ]
    chunk_size: int
    chunk_overlap: int = 0
    parent_chunk_size: int | None = None
    min_chunk_size: int | None = None
    boundary_rules: list[CustomBoundaryRule] = Field(default_factory=list)

    def factory_strategy(self) -> str:
        """factory에 전달할 전략명 — boundary_pattern은 clause_aware 재사용 (D3)."""
        return _FACTORY_STRATEGY[self.strategy]

    def factory_params(self) -> dict:
        """Design §3.2 매핑 — 미지정 optional은 생략해 factory 기본값을 쓴다."""
        if self.strategy == "full_token":
            return {
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            }
        if self.strategy == "parent_child":
            return self._with_parent_size({
                "child_chunk_size": self.chunk_size,
                "child_chunk_overlap": self.chunk_overlap,
            })
        if self.strategy == "semantic":
            return self._with_min_size({"chunk_size": self.chunk_size})
        if self.strategy == "section_aware":
            return self._with_min_size({
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            })
        return self._boundary_params()

    def display(self) -> dict:
        """문서별 청킹 이력 기록용 (D10) — 사용자 노출 전략명 유지."""
        display: dict = {
            "strategy": self.strategy,
            "custom": True,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }
        if self.parent_chunk_size is not None:
            display["parent_chunk_size"] = self.parent_chunk_size
        if self.min_chunk_size is not None:
            display["min_chunk_size"] = self.min_chunk_size
        if self.boundary_rules:
            display["boundary_rule_count"] = len(self.boundary_rules)
        return display

    def _boundary_params(self) -> dict:
        return self._with_parent_size({
            "parent_patterns": self._patterns_for("parent"),
            "child_patterns": self._patterns_for("child"),
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        })

    def _patterns_for(self, level: str) -> list[str]:
        rules = [r for r in self.boundary_rules if r.level == level]
        rules.sort(key=lambda r: r.priority)
        return [r.pattern for r in rules]

    def _with_parent_size(self, params: dict) -> dict:
        if self.parent_chunk_size is not None:
            params["parent_chunk_size"] = self.parent_chunk_size
        return params

    def _with_min_size(self, params: dict) -> dict:
        if self.min_chunk_size is not None:
            params["min_chunk_size"] = self.min_chunk_size
        return params


def parse_custom_chunking_config(raw: object) -> CustomChunkingConfig:
    """JSON 컬럼 값 → config 파싱. 실패는 ValueError로 통일 (V-06)."""
    try:
        return CustomChunkingConfig.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValueError(f"invalid custom_chunking_config: {exc}") from exc


class CustomChunkingPolicy:
    """커스텀 청킹 검증 규칙 V-01~V-07 (Design §4.2)."""

    MIN_SIZE_MIN = 50
    MIN_SIZE_MAX = 2000

    # V-03/V-05: 전략별 금지 파라미터 (Design §3.2 금지 열)
    _FORBIDDEN = {
        "full_token": ("parent_chunk_size", "min_chunk_size", "boundary_rules"),
        "parent_child": ("min_chunk_size", "boundary_rules"),
        "semantic": ("chunk_overlap", "parent_chunk_size", "boundary_rules"),
        "section_aware": ("parent_chunk_size", "boundary_rules"),
        STRATEGY_BOUNDARY_PATTERN: ("min_chunk_size",),
    }

    @classmethod
    def validate(cls, config: CustomChunkingConfig) -> None:
        cls._validate_ranges(config)
        cls._validate_forbidden(config)
        if config.strategy == STRATEGY_BOUNDARY_PATTERN:
            cls._validate_boundary_rules(config.boundary_rules)

    @classmethod
    def validate_kb_settings(
        cls,
        use_clause_chunking: bool,
        use_custom_chunking: bool,
        custom_chunking_config: dict | None,
    ) -> None:
        """KB 생성/수정 시 플래그·config 조합 검증 (V-06, V-07)."""
        if use_clause_chunking and use_custom_chunking:
            raise ValueError(
                "use_clause_chunking and use_custom_chunking "
                "cannot both be enabled"
            )
        if not use_custom_chunking:
            if custom_chunking_config is not None:
                raise ValueError(
                    "custom_chunking_config requires use_custom_chunking=true"
                )
            return
        if custom_chunking_config is None:
            raise ValueError(
                "custom_chunking_config is required "
                "when use_custom_chunking=true"
            )
        cls.validate(parse_custom_chunking_config(custom_chunking_config))

    @classmethod
    def _validate_ranges(cls, config: CustomChunkingConfig) -> None:
        p = ChunkingProfilePolicy
        if not (p.CHILD_SIZE_MIN <= config.chunk_size <= p.CHILD_SIZE_MAX):
            raise ValueError(
                f"chunk_size must be {p.CHILD_SIZE_MIN}~{p.CHILD_SIZE_MAX}"
            )
        if not (p.OVERLAP_MIN <= config.chunk_overlap <= p.OVERLAP_MAX):
            raise ValueError(
                f"chunk_overlap must be {p.OVERLAP_MIN}~{p.OVERLAP_MAX}"
            )
        if config.chunk_overlap >= config.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        cls._validate_optional_ranges(config)

    @classmethod
    def _validate_optional_ranges(cls, config: CustomChunkingConfig) -> None:
        p = ChunkingProfilePolicy
        if config.parent_chunk_size is not None:
            if not (
                p.PARENT_SIZE_MIN <= config.parent_chunk_size
                <= p.PARENT_SIZE_MAX
            ):
                raise ValueError(
                    f"parent_chunk_size must be "
                    f"{p.PARENT_SIZE_MIN}~{p.PARENT_SIZE_MAX}"
                )
            if config.chunk_size > config.parent_chunk_size:
                raise ValueError(
                    "chunk_size must not exceed parent_chunk_size"
                )
        if config.min_chunk_size is not None:
            if not (
                cls.MIN_SIZE_MIN <= config.min_chunk_size <= cls.MIN_SIZE_MAX
            ):
                raise ValueError(
                    f"min_chunk_size must be "
                    f"{cls.MIN_SIZE_MIN}~{cls.MIN_SIZE_MAX}"
                )
            if config.min_chunk_size >= config.chunk_size:
                raise ValueError(
                    "min_chunk_size must be less than chunk_size"
                )

    @classmethod
    def _validate_forbidden(cls, config: CustomChunkingConfig) -> None:
        for field_name in cls._FORBIDDEN[config.strategy]:
            if cls._is_set(config, field_name):
                raise ValueError(
                    f"'{config.strategy}' does not support {field_name}"
                )

    @staticmethod
    def _is_set(config: CustomChunkingConfig, field_name: str) -> bool:
        if field_name == "chunk_overlap":
            return config.chunk_overlap > 0
        if field_name == "boundary_rules":
            return bool(config.boundary_rules)
        return getattr(config, field_name) is not None

    @classmethod
    def _validate_boundary_rules(
        cls, rules: list[CustomBoundaryRule]
    ) -> None:
        p = ChunkingProfilePolicy
        if not rules:
            raise ValueError(
                "boundary_pattern strategy requires at least one boundary rule"
            )
        if len(rules) > p.MAX_RULES:
            raise ValueError(f"boundary_rules max {p.MAX_RULES} entries")
        if not any(r.level == "parent" for r in rules):
            raise ValueError("At least one 'parent' level rule is required")
        for rule in rules:
            cls._validate_pattern(rule.pattern)

    @classmethod
    def _validate_pattern(cls, pattern: str) -> None:
        if not pattern or not pattern.strip():
            raise ValueError("rule pattern must not be empty")
        if len(pattern) > ChunkingProfilePolicy.MAX_PATTERN_LENGTH:
            raise ValueError(
                f"rule pattern max "
                f"{ChunkingProfilePolicy.MAX_PATTERN_LENGTH} chars"
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex pattern '{pattern}': {exc}")
