"""DepartmentRepositoryInterface: 부서 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.department.entity import Department, UserDepartment


class DepartmentRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, dept: Department, request_id: str) -> Department: ...

    @abstractmethod
    async def find_by_id(self, dept_id: str, request_id: str) -> Department | None: ...

    @abstractmethod
    async def find_by_name(self, name: str, request_id: str) -> Department | None: ...

    @abstractmethod
    async def list_all(self, request_id: str) -> list[Department]: ...

    @abstractmethod
    async def update(self, dept: Department, request_id: str) -> Department: ...

    @abstractmethod
    async def delete(self, dept_id: str, request_id: str) -> None: ...

    @abstractmethod
    async def assign_user(self, ud: UserDepartment, request_id: str) -> None: ...

    @abstractmethod
    async def remove_user(
        self, user_id: int, department_id: str, request_id: str
    ) -> None: ...

    @abstractmethod
    async def find_departments_by_user(
        self, user_id: int, request_id: str
    ) -> list[UserDepartment]: ...

    @abstractmethod
    async def count_primary(self, user_id: int, request_id: str) -> int: ...
