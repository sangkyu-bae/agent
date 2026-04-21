"""Department 애플리케이션 레이어 스키마."""
from pydantic import BaseModel, Field


class CreateDepartmentRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=255)


class DepartmentResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


class DepartmentListResponse(BaseModel):
    departments: list[DepartmentResponse]


class UpdateDepartmentRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=255)


class AssignUserDepartmentRequest(BaseModel):
    department_id: str
    is_primary: bool = False
