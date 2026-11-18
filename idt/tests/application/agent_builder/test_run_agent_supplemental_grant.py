"""RunAgentUseCase → compile 로 SupplementalGrant 전달 (graph-rag-foundation §2.1, module-1).

- grant 미지정(None)이면 compile 호출 형태가 변경 전과 같다(인자 자체를 넘기지 않음)
- 대화 라우트가 넘긴 grant 는 그대로 compile 에 전달된다
"""
from unittest.mock import patch

import pytest
from src.domain.extension_hooks import SupplementalGrant

from tests.application.agent_builder.test_run_agent_memory_wiring import (
    _BIS,
    _agent,
    _auth_ctx,
    _request,
    _uc,
)


async def _compile_kwargs(uc, **extra):
    with patch(_BIS, return_value={}):
        await uc._prepare_graph(
            agent=_agent(), request=_request(), session_id="s", callback=None,
            run_id=None, request_id="req-1", auth_ctx=_auth_ctx(), **extra,
        )
    return uc._compiler.compile.call_args.kwargs


@pytest.mark.asyncio
async def test_no_grant_keeps_compile_call_shape():
    kwargs = await _compile_kwargs(_uc())
    assert "supplemental_grant" not in kwargs


@pytest.mark.asyncio
async def test_grant_forwarded_to_compile():
    grant = SupplementalGrant(caller_is_admin=True)
    kwargs = await _compile_kwargs(_uc(), supplemental_grant=grant)
    assert kwargs["supplemental_grant"] is grant
