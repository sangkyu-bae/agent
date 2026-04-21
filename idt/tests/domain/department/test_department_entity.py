"""Department / UserDepartment 도메인 엔티티 단위 테스트 (mock 금지)."""
from datetime import datetime, timezone

from src.domain.department.entity import Department, UserDepartment


class TestDepartment:
    def test_create_department(self):
        now = datetime.now(timezone.utc)
        dept = Department(
            id="dept-001",
            name="개발팀",
            description="소프트웨어 개발 부서",
            created_at=now,
            updated_at=now,
        )
        assert dept.id == "dept-001"
        assert dept.name == "개발팀"
        assert dept.description == "소프트웨어 개발 부서"
        assert dept.created_at == now
        assert dept.updated_at == now

    def test_create_department_without_description(self):
        now = datetime.now(timezone.utc)
        dept = Department(
            id="dept-002",
            name="디자인팀",
            description=None,
            created_at=now,
            updated_at=now,
        )
        assert dept.description is None

    def test_department_equality(self):
        now = datetime.now(timezone.utc)
        dept1 = Department(id="d1", name="팀A", description=None, created_at=now, updated_at=now)
        dept2 = Department(id="d1", name="팀A", description=None, created_at=now, updated_at=now)
        assert dept1 == dept2

    def test_department_inequality_different_id(self):
        now = datetime.now(timezone.utc)
        dept1 = Department(id="d1", name="팀A", description=None, created_at=now, updated_at=now)
        dept2 = Department(id="d2", name="팀A", description=None, created_at=now, updated_at=now)
        assert dept1 != dept2


class TestUserDepartment:
    def test_create_user_department(self):
        now = datetime.now(timezone.utc)
        ud = UserDepartment(
            user_id=1,
            department_id="dept-001",
            is_primary=True,
            created_at=now,
        )
        assert ud.user_id == 1
        assert ud.department_id == "dept-001"
        assert ud.is_primary is True
        assert ud.created_at == now

    def test_user_department_not_primary_by_default(self):
        now = datetime.now(timezone.utc)
        ud = UserDepartment(
            user_id=2,
            department_id="dept-002",
            is_primary=False,
            created_at=now,
        )
        assert ud.is_primary is False

    def test_user_department_equality(self):
        now = datetime.now(timezone.utc)
        ud1 = UserDepartment(user_id=1, department_id="d1", is_primary=True, created_at=now)
        ud2 = UserDepartment(user_id=1, department_id="d1", is_primary=True, created_at=now)
        assert ud1 == ud2

    def test_user_department_different_user(self):
        now = datetime.now(timezone.utc)
        ud1 = UserDepartment(user_id=1, department_id="d1", is_primary=True, created_at=now)
        ud2 = UserDepartment(user_id=2, department_id="d1", is_primary=True, created_at=now)
        assert ud1 != ud2
