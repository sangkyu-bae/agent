"""UserProfile 도메인 엔티티 단위 테스트 (mock 금지).

agent-user-context Design §3.4 검증.
"""
from datetime import date, datetime, timezone

import pytest

from src.domain.user_profile.entity import UserProfile


class TestUserProfile:
    def test_create_with_all_fields(self):
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            user_id=1,
            display_name="배상규",
            position="대리",
            employee_no="EMP-0001",
            joined_at=date(2020, 3, 1),
            created_at=now,
            updated_at=now,
        )
        assert profile.user_id == 1
        assert profile.display_name == "배상규"
        assert profile.position == "대리"
        assert profile.employee_no == "EMP-0001"
        assert profile.joined_at == date(2020, 3, 1)

    def test_create_with_minimal_fields(self):
        """position/employee_no/joined_at은 nullable."""
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            user_id=2,
            display_name="홍길동",
            position=None,
            employee_no=None,
            joined_at=None,
            created_at=now,
            updated_at=now,
        )
        assert profile.position is None
        assert profile.employee_no is None
        assert profile.joined_at is None

    def test_profile_is_frozen(self):
        """immutability — 요청 처리 중 변경 금지."""
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            user_id=1, display_name="A", position=None,
            employee_no=None, joined_at=None,
            created_at=now, updated_at=now,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            profile.display_name = "B"  # type: ignore[misc]

    def test_equality_by_value(self):
        now = datetime.now(timezone.utc)
        p1 = UserProfile(
            user_id=1, display_name="A", position=None,
            employee_no=None, joined_at=None,
            created_at=now, updated_at=now,
        )
        p2 = UserProfile(
            user_id=1, display_name="A", position=None,
            employee_no=None, joined_at=None,
            created_at=now, updated_at=now,
        )
        assert p1 == p2
