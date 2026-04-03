"""Domain 테스트: MCPServerRegistration 엔티티."""
from datetime import datetime

import pytest

from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


@pytest.fixture
def base_reg():
    return MCPServerRegistration(
        id="abc-123",
        user_id="user-1",
        name="My Tool",
        description="A great tool",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestMCPServerRegistrationToolId:

    def test_tool_id_has_mcp_prefix(self, base_reg):
        assert base_reg.tool_id == "mcp_abc-123"

    def test_tool_id_uses_entity_id(self):
        reg = MCPServerRegistration(
            id="xyz-999",
            user_id="u",
            name="T",
            description="D",
            endpoint="https://a.com/sse",
            transport=MCPTransportType.SSE,
            input_schema=None,
            is_active=True,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert reg.tool_id == "mcp_xyz-999"


class TestMCPServerRegistrationApplyUpdate:

    def test_apply_update_changes_name(self, base_reg):
        new_dt = datetime(2026, 2, 1)
        base_reg.apply_update(
            name="New Name",
            description=None,
            endpoint=None,
            input_schema=None,
            is_active=None,
            updated_at=new_dt,
        )
        assert base_reg.name == "New Name"
        assert base_reg.updated_at == new_dt

    def test_apply_update_does_not_change_unset_fields(self, base_reg):
        base_reg.apply_update(
            name=None,
            description=None,
            endpoint=None,
            input_schema=None,
            is_active=None,
            updated_at=datetime(2026, 2, 1),
        )
        assert base_reg.name == "My Tool"
        assert base_reg.description == "A great tool"
        assert base_reg.endpoint == "https://mcp.example.com/sse"

    def test_apply_update_changes_endpoint(self, base_reg):
        base_reg.apply_update(
            name=None,
            description=None,
            endpoint="https://new.example.com/sse",
            input_schema=None,
            is_active=None,
            updated_at=datetime(2026, 2, 1),
        )
        assert base_reg.endpoint == "https://new.example.com/sse"

    def test_apply_update_deactivates(self, base_reg):
        base_reg.apply_update(
            name=None, description=None, endpoint=None,
            input_schema=None, is_active=False,
            updated_at=datetime(2026, 2, 1),
        )
        assert base_reg.is_active is False

    def test_apply_update_sets_input_schema(self, base_reg):
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        base_reg.apply_update(
            name=None, description=None, endpoint=None,
            input_schema=schema, is_active=None,
            updated_at=datetime(2026, 2, 1),
        )
        assert base_reg.input_schema == schema


class TestMCPServerRegistrationConvenienceMethods:

    def test_deactivate_sets_is_active_false(self, base_reg):
        base_reg.deactivate()
        assert base_reg.is_active is False

    def test_activate_sets_is_active_true(self, base_reg):
        base_reg.is_active = False
        base_reg.activate()
        assert base_reg.is_active is True
