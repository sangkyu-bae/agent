"""MemoryPolicy — 메모리 검증·주입 순서·예산 절단 순수 규칙 (agent-memory Design §3-2).

외부 시스템 호출 없음. 상한 값 자체(max_count/token_cap)는 config에서 주입받는다.
"""
from src.domain.memory.entity import Memory, MemoryType


class MemoryPolicy:
    CONTENT_MAX = 500

    # 주입 우선순위 (작을수록 먼저) — 동순위는 최신(updated_at desc)
    TYPE_PRIORITY = {
        MemoryType.PROFILE: 0,
        MemoryType.DOMAIN_TERM: 1,
        MemoryType.PREFERENCE: 2,
        MemoryType.EPISODE: 3,
    }

    # Design 결정 ④: 한글 최악 기준 1자≈1토큰 보수 근사 — 캡은 문자 예산으로 적용
    CHARS_PER_TOKEN = 1

    # Phase 2 추출 (agent-memory-extraction 결정 ①)
    EXTRACT_INPUT_MAX = 4000  # question+answer 합산 절단
    CONFIDENCE_MIN = 0
    CONFIDENCE_MAX = 100

    @staticmethod
    def validate_content(content: str) -> None:
        """빈 내용(공백만 포함) 또는 CONTENT_MAX 초과 시 ValueError."""
        if not content or not content.strip():
            raise ValueError("메모리 내용이 비어 있습니다.")
        if len(content) > MemoryPolicy.CONTENT_MAX:
            raise ValueError(
                f"메모리 내용은 {MemoryPolicy.CONTENT_MAX}자를 초과할 수 없습니다."
            )

    @staticmethod
    def validate_active_count(current_count: int, max_count: int) -> None:
        """활성 메모리 개수 상한 도달 시 ValueError — 라우터에서 422로 매핑."""
        if current_count >= max_count:
            raise ValueError(
                f"메모리 개수 상한({max_count}개)에 도달했습니다. "
                "기존 메모리를 삭제한 뒤 다시 등록하세요."
            )

    @staticmethod
    def sort_for_injection(memories: list[Memory]) -> list[Memory]:
        """TYPE_PRIORITY asc → updated_at desc. 원본 목록은 변경하지 않는다."""
        from datetime import datetime

        # timestamp() 변환 없이 이중 안정 정렬 — datetime.min도 안전하게 비교 가능
        by_recent = sorted(
            memories, key=lambda m: m.updated_at or datetime.min, reverse=True
        )
        return sorted(by_recent, key=lambda m: MemoryPolicy.TYPE_PRIORITY[m.mem_type])

    @staticmethod
    def validate_transition(memory: Memory) -> None:
        """승인/거부는 승인 대기(PENDING) 상태에서만 가능 — 라우터에서 422."""
        from src.domain.memory.entity import MemoryStatus

        if memory.status != MemoryStatus.PENDING:
            raise ValueError("승인 대기 상태의 메모리만 승인/거부할 수 있습니다.")

    @staticmethod
    def clamp_confidence(value: int) -> int:
        """LLM 자체 평가 confidence를 0~100으로 clamp."""
        return max(MemoryPolicy.CONFIDENCE_MIN, min(MemoryPolicy.CONFIDENCE_MAX, value))

    @staticmethod
    def dedup_candidates(candidates: list, existing_contents: set[str]) -> list:
        """content.strip() 정확 일치 기준 중복 제거 (FR-04).

        기존 메모리와 일치하는 후보 + 후보 목록 내 중복을 제거한다.
        candidates는 content 속성만 요구 (duck-typed — application 타입 미참조).
        """
        normalized_existing = {c.strip() for c in existing_contents}
        seen: set[str] = set()
        result = []
        for candidate in candidates:
            key = candidate.content.strip()
            if key in normalized_existing or key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    @staticmethod
    def sort_for_injection_scoped(memories: list[Memory]) -> list[Memory]:
        """개인(user) 우선 → 부서(org), 각 스코프 내 TYPE_PRIORITY → 최신순.

        agent-memory-org-scope 결정 ③: 개인 맥락이 부서 일반론보다 우선 주입된다.
        원본 목록은 변경하지 않는다.
        """
        from datetime import datetime

        from src.domain.memory.entity import MemoryScope

        def _scope_rank(m: Memory) -> int:
            return 0 if m.scope == MemoryScope.USER else 1

        by_recent = sorted(
            memories, key=lambda m: m.updated_at or datetime.min, reverse=True
        )
        by_type = sorted(by_recent, key=lambda m: MemoryPolicy.TYPE_PRIORITY[m.mem_type])
        return sorted(by_type, key=_scope_rank)

    @staticmethod
    def truncate_to_budget(
        memories: list[Memory], token_cap: int
    ) -> tuple[list[Memory], bool]:
        """정렬된 목록을 문자 예산(token_cap × CHARS_PER_TOKEN) 내로 절단.

        Returns:
            (포함 목록, 절단 발생 여부) — 절단 시 호출부가 debug 로그(FR-05).
        """
        budget = token_cap * MemoryPolicy.CHARS_PER_TOKEN
        included: list[Memory] = []
        used = 0
        for memory in memories:
            cost = len(memory.content)
            if used + cost > budget:
                return included, True
            included.append(memory)
            used += cost
        return included, False
