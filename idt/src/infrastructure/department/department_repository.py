"""DepartmentRepository: departments + user_departments MySQL CRUD."""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.department.entity import Department, UserDepartment
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.department.models import DepartmentModel, UserDepartmentModel


class DepartmentRepository(DepartmentRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, dept: Department, request_id: str) -> Department:
        self._logger.info("Department save", request_id=request_id, dept_id=dept.id)
        try:
            model = DepartmentModel(
                id=dept.id,
                name=dept.name,
                description=dept.description,
                created_at=dept.created_at,
                updated_at=dept.updated_at,
            )
            self._session.add(model)
            await self._session.flush()
            return dept
        except Exception as e:
            self._logger.error("Department save failed", exception=e, request_id=request_id)
            raise

    async def find_by_id(self, dept_id: str, request_id: str) -> Department | None:
        self._logger.info("Department find_by_id", request_id=request_id, dept_id=dept_id)
        try:
            stmt = select(DepartmentModel).where(DepartmentModel.id == dept_id)
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error("Department find_by_id failed", exception=e, request_id=request_id)
            raise

    async def find_by_name(self, name: str, request_id: str) -> Department | None:
        self._logger.info("Department find_by_name", request_id=request_id, name=name)
        try:
            stmt = select(DepartmentModel).where(DepartmentModel.name == name)
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error("Department find_by_name failed", exception=e, request_id=request_id)
            raise

    async def list_all(self, request_id: str) -> list[Department]:
        self._logger.info("Department list_all", request_id=request_id)
        try:
            stmt = select(DepartmentModel).order_by(DepartmentModel.name)
            result = await self._session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
        except Exception as e:
            self._logger.error("Department list_all failed", exception=e, request_id=request_id)
            raise

    async def update(self, dept: Department, request_id: str) -> Department:
        self._logger.info("Department update", request_id=request_id, dept_id=dept.id)
        try:
            stmt = select(DepartmentModel).where(DepartmentModel.id == dept.id)
            result = await self._session.execute(stmt)
            model = result.scalar_one()
            model.name = dept.name
            model.description = dept.description
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            return dept
        except Exception as e:
            self._logger.error("Department update failed", exception=e, request_id=request_id)
            raise

    async def delete(self, dept_id: str, request_id: str) -> None:
        self._logger.info("Department delete", request_id=request_id, dept_id=dept_id)
        try:
            stmt = delete(DepartmentModel).where(DepartmentModel.id == dept_id)
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error("Department delete failed", exception=e, request_id=request_id)
            raise

    async def assign_user(self, ud: UserDepartment, request_id: str) -> None:
        self._logger.info(
            "UserDepartment assign",
            request_id=request_id,
            user_id=ud.user_id,
            dept_id=ud.department_id,
        )
        try:
            model = UserDepartmentModel(
                user_id=ud.user_id,
                department_id=ud.department_id,
                is_primary=ud.is_primary,
                created_at=ud.created_at,
            )
            self._session.add(model)
            await self._session.flush()
        except Exception as e:
            self._logger.error("UserDepartment assign failed", exception=e, request_id=request_id)
            raise

    async def remove_user(
        self, user_id: int, department_id: str, request_id: str
    ) -> None:
        self._logger.info(
            "UserDepartment remove",
            request_id=request_id,
            user_id=user_id,
            dept_id=department_id,
        )
        try:
            stmt = delete(UserDepartmentModel).where(
                UserDepartmentModel.user_id == user_id,
                UserDepartmentModel.department_id == department_id,
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error("UserDepartment remove failed", exception=e, request_id=request_id)
            raise

    async def find_departments_by_user(
        self, user_id: int, request_id: str
    ) -> list[UserDepartment]:
        self._logger.info(
            "UserDepartment find_by_user", request_id=request_id, user_id=user_id
        )
        try:
            stmt = select(UserDepartmentModel).where(
                UserDepartmentModel.user_id == user_id
            )
            result = await self._session.execute(stmt)
            return [
                UserDepartment(
                    user_id=m.user_id,
                    department_id=m.department_id,
                    is_primary=m.is_primary,
                    created_at=m.created_at,
                )
                for m in result.scalars().all()
            ]
        except Exception as e:
            self._logger.error(
                "UserDepartment find_by_user failed", exception=e, request_id=request_id
            )
            raise

    async def count_primary(self, user_id: int, request_id: str) -> int:
        self._logger.info(
            "UserDepartment count_primary", request_id=request_id, user_id=user_id
        )
        try:
            stmt = select(func.count()).where(
                UserDepartmentModel.user_id == user_id,
                UserDepartmentModel.is_primary == True,  # noqa: E712
            )
            result = await self._session.execute(stmt)
            return result.scalar_one()
        except Exception as e:
            self._logger.error(
                "UserDepartment count_primary failed", exception=e, request_id=request_id
            )
            raise

    def _to_domain(self, model: DepartmentModel) -> Department:
        return Department(
            id=model.id,
            name=model.name,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
