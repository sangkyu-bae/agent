"""approval-gate: ApprovalPolicy / ApprovalSignalPolicy 단위 테스트.

Design Ref: §2.2 (게이트 발동 합성 규칙·상태 기계), §9.3 (도메인 순수성).
DB·langchain 없이 전부 돌아간다 — Option C가 미들웨어를 순수하게 유지한 결과.
"""
from datetime import datetime, timedelta

import pytest

from src.domain.approval.entity import ApprovalStatus, GateSettings
from src.domain.approval.policies import ApprovalPolicy, ApprovalSignalPolicy

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _gate(
    *,
    mode: str = "always",
    execute_after: str | None = None,
    expires_hours: int = 168,
    is_enforced: bool = False,
) -> GateSettings:
    return GateSettings(
        mode=mode,
        execute_after=execute_after,
        expires_hours=expires_hours,
        is_enforced=is_enforced,
    )


class TestGateSettingsFromConfig:
    def test_빈_config는_기본값(self):
        s = GateSettings.from_config({}, is_enforced=False)
        assert s.mode == "always"
        assert s.execute_after is None
        assert s.expires_hours == ApprovalPolicy.DEFAULT_EXPIRES_HOURS

    def test_config_값이_반영된다(self):
        s = GateSettings.from_config(
            {"mode": "off", "execute_after": "0 0 * * *", "expires_hours": 24},
            is_enforced=True,
        )
        assert (s.mode, s.execute_after, s.expires_hours) == ("off", "0 0 * * *", 24)
        assert s.is_enforced is True

    def test_expires_hours는_상하한으로_clamp된다(self):
        """클라이언트·관리자 입력을 도메인이 최종 방어한다 (SlotLimits 선례)."""
        assert GateSettings.from_config(
            {"expires_hours": 0}, is_enforced=False
        ).expires_hours == ApprovalPolicy.MIN_EXPIRES_HOURS
        assert GateSettings.from_config(
            {"expires_hours": 9999}, is_enforced=False
        ).expires_hours == ApprovalPolicy.MAX_EXPIRES_HOURS


class TestShouldGate:
    """Design §2.2 — 도구 축 AND 에이전트 축의 합성."""

    def test_도구가_승인대상이고_게이트_적용이면_발동(self):
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=True, gate=_gate()
        ) is True

    def test_도구가_승인대상이_아니면_미발동(self):
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=False, gate=_gate()
        ) is False

    def test_게이트_미적용이면_미발동(self):
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=True, gate=None
        ) is False

    def test_enforced여도_도구가_승인대상이_아니면_미발동(self):
        """관리자 강제가 무해한 에이전트까지 멈추지 않는다 (Plan §5 리스크)."""
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=False, gate=_gate(is_enforced=True)
        ) is False

    def test_mode_off면_미발동(self):
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=True, gate=_gate(mode="off")
        ) is False

    def test_enforced는_mode_off를_무시하고_발동(self):
        """안전 기능의 끌 권한을 당사자에게 주지 않는다 (Design §7)."""
        assert ApprovalPolicy.should_gate(
            tool_requires_approval=True,
            gate=_gate(mode="off", is_enforced=True),
        ) is True


class TestCanDecide:
    def test_에이전트_소유자는_승인_가능(self):
        assert ApprovalPolicy.can_decide(user_id="u1", agent_owner_id="u1") is True

    def test_타인은_승인_불가(self):
        assert ApprovalPolicy.can_decide(user_id="u2", agent_owner_id="u1") is False

    def test_빈_사용자는_승인_불가(self):
        """시스템 신원(스케줄·웹훅)이 자기 자신을 승인하지 못하게 한다."""
        assert ApprovalPolicy.can_decide(user_id="", agent_owner_id="") is False


class TestNextStatus:
    @pytest.mark.parametrize(
        ("current", "event", "expected"),
        [
            ("pending", "approve", "approved"),
            ("pending", "reject", "rejected"),
            ("pending", "expire", "expired"),
            ("approved", "schedule", "scheduled"),
            ("approved", "execute", "executed"),
            ("approved", "fail", "failed"),
            ("scheduled", "execute", "executed"),
            ("scheduled", "fail", "failed"),
            ("scheduled", "expire", "expired"),
        ],
    )
    def test_허용_전이(self, current, event, expected):
        assert ApprovalPolicy.next_status(current, event) == expected

    @pytest.mark.parametrize(
        ("current", "event"),
        [
            ("executed", "approve"),   # 역전이
            ("rejected", "approve"),
            ("expired", "approve"),
            ("pending", "execute"),    # 건너뛰기
            ("pending", "schedule"),
            ("failed", "execute"),     # 자동 재시도 금지 (FR-25)
        ],
    )
    def test_금지_전이는_ValueError(self, current, event):
        with pytest.raises(ValueError):
            ApprovalPolicy.next_status(current, event)

    def test_미지_이벤트는_ValueError(self):
        with pytest.raises(ValueError):
            ApprovalPolicy.next_status("pending", "없는이벤트")


class TestExpiry:
    def test_만료_시각_계산(self):
        assert ApprovalPolicy.resolve_expires_at(_NOW, 24) == _NOW + timedelta(hours=24)

    def test_만료_경과_판정(self):
        assert ApprovalPolicy.is_expired(_NOW - timedelta(seconds=1), now=_NOW) is True

    def test_만료_시각_정각은_아직_유효하지_않다(self):
        """경계는 만료로 본다 — 애매한 순간에 집행하지 않는 쪽이 안전하다."""
        assert ApprovalPolicy.is_expired(_NOW, now=_NOW) is True

    def test_미래는_유효(self):
        assert ApprovalPolicy.is_expired(_NOW + timedelta(hours=1), now=_NOW) is False


class TestValidateWindow:
    """FR-26 — 영원히 집행되지 않는 조합을 승인 시점에 차단."""

    def test_집행이_만료보다_늦으면_거부(self):
        with pytest.raises(ValueError):
            ApprovalPolicy.validate_window(
                execute_after=_NOW + timedelta(hours=10),
                expires_at=_NOW + timedelta(hours=1),
            )

    def test_집행이_만료보다_이르면_통과(self):
        ApprovalPolicy.validate_window(
            execute_after=_NOW + timedelta(hours=1),
            expires_at=_NOW + timedelta(hours=10),
        )

    def test_즉시_집행은_항상_통과(self):
        ApprovalPolicy.validate_window(
            execute_after=None, expires_at=_NOW + timedelta(hours=1)
        )


class TestIdempotencyKey:
    def test_구성요소_3종으로_생성(self):
        key = ApprovalPolicy.build_idempotency_key(
            run_id="r1", worker_id="w1", tool_call_id="tc1"
        )
        assert key == "r1:w1:tc1"

    def test_같은_입력은_같은_키(self):
        a = ApprovalPolicy.build_idempotency_key(
            run_id="r1", worker_id="w1", tool_call_id="tc1"
        )
        b = ApprovalPolicy.build_idempotency_key(
            run_id="r1", worker_id="w1", tool_call_id="tc1"
        )
        assert a == b

    def test_tool_call_id가_없으면_ValueError(self):
        """키가 비면 UNIQUE 제약이 무력해져 이중 집행이 열린다."""
        with pytest.raises(ValueError):
            ApprovalPolicy.build_idempotency_key(
                run_id="r1", worker_id="w1", tool_call_id=""
            )


class _Msg:
    """ToolMessage 최소 대역 — langchain 의존 없이 트레이스를 흉내낸다."""

    def __init__(self, content: str) -> None:
        self.content = content


class TestApprovalSignalPolicy:
    """render ↔ extract 왕복이 같은 Policy에 있어 포맷이 어긋나지 않는다."""

    def test_렌더_결과를_다시_파싱할_수_있다(self):
        rendered = ApprovalSignalPolicy.render(
            tool_id="email_send",
            tool_args={"to": "a@b.c", "subject": "안녕"},
            draft="본문입니다",
            tool_call_id="tc1",
        )
        signal = ApprovalSignalPolicy.extract([_Msg(rendered)])
        assert signal is not None
        assert signal.tool_id == "email_send"
        assert signal.tool_args == {"to": "a@b.c", "subject": "안녕"}
        assert signal.draft == "본문입니다"
        assert signal.tool_call_id == "tc1"

    def test_마커가_없으면_None(self):
        assert ApprovalSignalPolicy.extract([_Msg("평범한 도구 결과")]) is None

    def test_빈_트레이스는_None(self):
        assert ApprovalSignalPolicy.extract([]) is None

    def test_여러_메시지_중_마커를_찾는다(self):
        rendered = ApprovalSignalPolicy.render(
            tool_id="t", tool_args={}, draft="d", tool_call_id="tc"
        )
        signal = ApprovalSignalPolicy.extract(
            [_Msg("앞"), _Msg(rendered), _Msg("뒤")]
        )
        assert signal is not None and signal.tool_id == "t"

    def test_마커가_여러_개면_첫_번째만(self):
        """런당 pending 1건 불변식(FR-06) — 첫 신호만 채택한다."""
        first = ApprovalSignalPolicy.render(
            tool_id="first", tool_args={}, draft="", tool_call_id="tc1"
        )
        second = ApprovalSignalPolicy.render(
            tool_id="second", tool_args={}, draft="", tool_call_id="tc2"
        )
        signal = ApprovalSignalPolicy.extract([_Msg(first), _Msg(second)])
        assert signal is not None and signal.tool_id == "first"

    def test_깨진_마커는_None(self):
        """파싱 실패가 예외로 번져 워커를 죽이지 않는다."""
        broken = f"{ApprovalSignalPolicy.MARKER}{{잘못된 json"
        assert ApprovalSignalPolicy.extract([_Msg(broken)]) is None

    def test_content가_문자열이_아니어도_죽지_않는다(self):
        assert ApprovalSignalPolicy.extract([_Msg(["블록", "리스트"])]) is None

    def test_한글_초안이_왕복에서_보존된다(self):
        draft = "기준금리를 3.50% → 3.25%로 변경합니다"
        rendered = ApprovalSignalPolicy.render(
            tool_id="rate_update", tool_args={"rate": 3.25}, draft=draft,
            tool_call_id="tc",
        )
        signal = ApprovalSignalPolicy.extract([_Msg(rendered)])
        assert signal is not None and signal.draft == draft


class TestSnapshotLimit:
    def test_상한_이하는_그대로(self):
        assert ApprovalPolicy.exceeds_snapshot_limit(b"x" * 100) is False

    def test_상한_초과_판정(self):
        oversize = b"x" * (ApprovalPolicy.MAX_SNAPSHOT_BYTES + 1)
        assert ApprovalPolicy.exceeds_snapshot_limit(oversize) is True


class TestStatusLiteral:
    def test_상태_집합이_설계와_일치한다(self):
        assert set(ApprovalStatus.__args__) == {
            "pending", "approved", "scheduled",
            "executed", "rejected", "expired", "failed",
        }


class TestNextExecuteAfter:
    """Check G13 — 예약 집행 시각은 사용자 타임존 기준이어야 한다.

    이전 구현은 cron 을 UTC naive 로 계산해 '0 0 * * *' 가 KST 오전 9시에
    발화했다. 이전 테스트가 UTC 입력 → UTC 기대값으로 비교해 이 결함을
    드러내지 못했으므로, 여기서는 반드시 KST 벽시계로 기대값을 적는다.
    """

    def test_KST_자정은_UTC_15시다(self):
        # 저녁 승인: 2026-09-21 18:00 KST == 09:00 UTC
        now_utc = datetime(2026, 9, 21, 9, 0, 0)
        nxt = ApprovalPolicy.next_execute_after(
            "0 0 * * *", now_utc=now_utc, tz="Asia/Seoul"
        )
        # 다음 KST 00:00 == 2026-09-21 15:00 UTC
        assert nxt == datetime(2026, 9, 21, 15, 0, 0)

    def test_결과는_UTC_naive다(self):
        """DB DATETIME 규격 (agent_schedule 관례)."""
        nxt = ApprovalPolicy.next_execute_after(
            "0 0 * * *", now_utc=datetime(2026, 9, 21, 9), tz="Asia/Seoul"
        )
        assert nxt.tzinfo is None

    def test_KST_자정_직전_승인은_곧바로_그_자정(self):
        # 23:30 KST == 14:30 UTC → 30분 뒤 00:00 KST
        nxt = ApprovalPolicy.next_execute_after(
            "0 0 * * *", now_utc=datetime(2026, 9, 21, 14, 30), tz="Asia/Seoul"
        )
        assert nxt == datetime(2026, 9, 21, 15, 0, 0)

    def test_KST_자정_직후_승인은_다음날_자정(self):
        # 00:10 KST(9/22) == 15:10 UTC(9/21) → 다음 00:00 KST 는 9/23
        nxt = ApprovalPolicy.next_execute_after(
            "0 0 * * *", now_utc=datetime(2026, 9, 21, 15, 10), tz="Asia/Seoul"
        )
        assert nxt == datetime(2026, 9, 22, 15, 0, 0)

    def test_UTC_타임존이면_그대로(self):
        nxt = ApprovalPolicy.next_execute_after(
            "0 0 * * *", now_utc=datetime(2026, 9, 21, 9), tz="UTC"
        )
        assert nxt == datetime(2026, 9, 22, 0, 0, 0)

    def test_cron이_없으면_None_즉시집행(self):
        assert ApprovalPolicy.next_execute_after(
            None, now_utc=datetime(2026, 9, 21, 9), tz="Asia/Seoul"
        ) is None

    def test_기본_타임존은_서울(self):
        assert ApprovalPolicy.DEFAULT_TIMEZONE == "Asia/Seoul"


class TestGateSettingsTimezone:
    def test_config에_없으면_기본_타임존(self):
        s = GateSettings.from_config({}, is_enforced=False)
        assert s.timezone == "Asia/Seoul"

    def test_config_타임존이_반영된다(self):
        s = GateSettings.from_config({"timezone": "UTC"}, is_enforced=False)
        assert s.timezone == "UTC"
