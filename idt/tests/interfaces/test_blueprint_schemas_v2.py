"""interfaces/schemas/blueprint — schema v2 라운드트립 (blueprint-style-fidelity §4.1).

extra="forbid" 라 v2 필드를 스키마에 추가하지 않으면 프론트 PUT 이 400 으로 깨진다.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.interfaces.schemas.blueprint import BlueprintPayload, BlueprintResponse

_V1 = Path(__file__).parents[1] / "fixtures" / "blueprint" / "golden_v1.json"


def _payload_dict() -> dict:
    data = json.loads(_V1.read_text(encoding="utf-8"))
    data.pop("created_at"), data.pop("updated_at")
    return data


def test_v1_payload_still_accepted():
    bp = BlueprintPayload.model_validate(_payload_dict()).to_domain()
    assert bp.schema_version == 1 and bp.patterns[0].decorations == ()


def test_v2_fields_roundtrip_through_payload_and_response():
    data = _payload_dict()
    data["schema_version"] = 2
    deco = {
        "id": "deco1",
        "shape": "rect",
        "box": {"x": 0, "y": 0.93, "w": 1, "h": 0.07},
        "fill": "#F2F4F5",
        "line": None,
    }
    data["style"]["common_decorations"] = [deco]
    data["style"]["header_footer"].update(
        footer_box={"x": 0.06, "y": 0.95, "w": 0.5, "h": 0.04},
        page_number_box={"x": 0.9, "y": 0.95, "w": 0.08, "h": 0.04},
        footer_color="#666666",
    )
    card_box = {"x": 0.06, "y": 0.22, "w": 0.88, "h": 0.15}
    data["patterns"][2]["decorations"] = [{**deco, "box": card_box}]
    data["patterns"][0]["slots"][1]["align"] = "center"
    data["assets"][1]["cover_box"] = {"x": 0.06, "y": 0.07, "w": 0.19, "h": 0.11}

    bp = BlueprintPayload.model_validate(data).to_domain()
    assert bp.schema_version == 2
    assert bp.style.common_decorations[0].fill == "#F2F4F5"
    assert bp.patterns[2].decorations[0].box.y == 0.22
    assert bp.patterns[0].slots[1].align == "center"
    assert bp.style.header_footer.footer_color == "#666666"
    assert bp.assets[1].cover_box is not None

    out = BlueprintResponse.from_domain(bp).model_dump()
    assert out["style"]["common_decorations"][0]["id"] == "deco1"
    assert out["patterns"][0]["slots"][1]["align"] == "center"
    # 응답을 그대로 다시 PUT 할 수 있어야 한다 (프론트 라운드트립)
    out.pop("created_at"), out.pop("updated_at")
    again = BlueprintPayload.model_validate(out).to_domain()
    assert replace(again, created_at=bp.created_at, updated_at=bp.updated_at) == bp


def test_unknown_field_still_forbidden():
    data = _payload_dict()
    data["patterns"][0]["slots"][0]["color"] = "#000000"
    with pytest.raises(ValidationError):
        BlueprintPayload.model_validate(data)


def test_default_schema_version_is_current():
    data = _payload_dict()
    data.pop("schema_version")
    assert BlueprintPayload.model_validate(data).schema_version == 2
