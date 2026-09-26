"""capability_denial_patterns 설정 계약.

Design Ref: worker-capability-denial-guard §3.3 (D-03) / Plan SC: FR-03

패턴은 코어 상수가 아니라 설정값이다 — 배포 없이 환경변수로 조정한다.
"""
from src.config import Settings


def _split(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw.split(",") if p.strip())


class TestCapabilityDenialPatternsSetting:

    def test_default_contains_measured_denial_phrases(self):
        """기본값은 실측 워커 산출(런 031564e4)의 문구를 덮는다."""
        patterns = _split(Settings().capability_denial_patterns)
        assert "어떤 도구로도" in patterns
        assert "권한/범위 밖" in patterns

    def test_default_excludes_legitimate_worker_scope_note(self):
        """early-finish-fix D-08 권장 표기는 오탐 대상이 아니다."""
        patterns = _split(Settings().capability_denial_patterns)
        assert all("이 워커의 범위 밖" not in p for p in patterns)

    def test_default_has_no_overly_short_superstring(self):
        """'할 수 없습니다'류 짧은 상위 문자열은 무관한 문맥까지 잡는다."""
        patterns = _split(Settings().capability_denial_patterns)
        assert "할 수 없습니다" not in patterns
        assert all(len(p) >= 5 for p in patterns)

    def test_env_override_replaces_default(self, monkeypatch):
        monkeypatch.setenv("CAPABILITY_DENIAL_PATTERNS", "커스텀 문구 A, 커스텀 문구 B")
        patterns = _split(Settings().capability_denial_patterns)
        assert patterns == ("커스텀 문구 A", "커스텀 문구 B")

    def test_empty_env_disables_detection(self, monkeypatch):
        """빈 문자열이면 패턴 튜플이 비어 CapabilityDenialPolicy가 꺼진다."""
        monkeypatch.setenv("CAPABILITY_DENIAL_PATTERNS", "")
        assert _split(Settings().capability_denial_patterns) == ()
