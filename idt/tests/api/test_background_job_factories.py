"""create_background_job_factories 회귀 테스트.

GET /api/v1/schedules 요청 시 my_schedules_f 가 NameError
(ScheduleRepository 미import)로 500 을 내던 결함을 고정한다.
"""
from unittest.mock import MagicMock

from src.api.main import create_background_job_factories
from src.application.background_job.list_my_schedules_use_case import (
    ListMySchedulesUseCase,
)


def test_my_schedules_factory_builds_use_case_without_name_error():
    factories = create_background_job_factories(build_run_agent_uc=MagicMock())
    my_schedules_f = factories[9]

    use_case = my_schedules_f(session=MagicMock())

    assert isinstance(use_case, ListMySchedulesUseCase)
