"""admin_blueprint_router — Design §8.2 #1~#13 (UseCase fake, 에러 매핑·직렬화)."""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.admin_blueprint_router import (
    get_blueprint_admin_use_case,
    get_blueprint_extraction_use_case,
    get_blueprint_thumbnailer,
    options_router,
    router,
)
from src.application.blueprint.extraction_use_case import ExtractionOutcome
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.blueprint.errors import (
    BlueprintNotFoundError,
    BlueprintValidationError,
    SampleExtractionError,
    UnsupportedSampleFormatError,
)
from src.domain.blueprint.interfaces import StoredAsset
from src.domain.blueprint.serialization import blueprint_to_dict
from src.domain.blueprint.value_objects import (
    BlueprintAsset,
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PatternKind,
    RelBox,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.domain.multimodal.errors import MultimodalNotConfiguredError
from src.interfaces.dependencies.auth import get_current_user

BASE = "/api/v1/admin/blueprints"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def _user(role=UserRole.ADMIN) -> User:
    return User(
        email="a@t.com", password_hash="h", role=role, status=UserStatus.APPROVED, id=7
    )


def _bp(bid="b1") -> DocumentBlueprint:
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    asset = BlueprintAsset(
        "a1", "logo", "image/png", 10, 5, "f" * 64, RelBox(0.8, 0.02, 0.1, 0.05), True
    )
    slot = Slot(
        "title", SlotKind.TITLE, RelBox(0.1, 0.1, 0.8, 0.2), "t", 40, None, None
    )
    return DocumentBlueprint(
        id=bid,
        name="샘플",
        description="",
        schema_version=1,
        source_kind="pdf",
        page_count=1,
        style=StyleTokens(
            (13.333, 7.5),
            {"heading": "H", "body": "B"},
            {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
            {
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", False),
            HeaderFooter("a1", "{n}", ""),
        ),
        patterns=(PagePattern("p1", PatternKind.COVER, (slot,), None, 1, ""),),
        narrative=Narrative((NarrativeSection("표지", ("p1",), ""),), "", "ko"),
        assets=(asset,),
        font_mapping={"H": "X"},
        warnings=("w",),
        status="active",
        created_at=now,
        updated_at=now,
    )


def _payload(bp: DocumentBlueprint) -> dict:
    d = blueprint_to_dict(bp)
    d.pop("created_at")
    d.pop("updated_at")
    return d


def _client(extraction=None, admin=None, user=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(options_router)
    app.dependency_overrides[get_blueprint_extraction_use_case] = lambda: (
        extraction or MagicMock()
    )
    app.dependency_overrides[get_blueprint_admin_use_case] = lambda: (
        admin or MagicMock()
    )
    app.dependency_overrides[get_blueprint_thumbnailer] = lambda: lambda b: "thumb"
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _outcome() -> ExtractionOutcome:
    bp = _bp()
    return ExtractionOutcome(
        blueprint=bp,
        assets={"a1": PNG},
        page_thumbnails=(PNG, None),
        classification=(1, 1),
        timings_ms={"extract": 1, "classify": 2, "synthesize": 3},
    )


# ── extract ───────────────────────────────────────────────────────────────────


def test_extract_ok_returns_draft_assets_and_thumbnails():
    uc = MagicMock()
    uc.run = AsyncMock(return_value=_outcome())
    r = _client(extraction=uc).post(
        f"{BASE}/extract?max_pages=10",
        files={"file": ("s.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["draft"]["id"] == "b1" and b["draft"]["patterns"][0]["kind"] == "cover"
    assert (
        b["assets"][0]["thumbnail_b64"] == "thumb" and b["assets"][0]["kind"] == "logo"
    )
    assert b["page_thumbnails"] == ["thumb", None]
    assert base64.b64decode(b["assets"][0]["data_b64"]) == PNG  # 저장 시 되돌려 보냄
    assert b["classification"] == {"succeeded": 1, "failed": 1}
    assert uc.run.await_args.args[1:3] == ("s.pdf", 10)


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (UnsupportedSampleFormatError("docx", ("pdf",)), 415, "UNSUPPORTED_MEDIA"),
        (SampleExtractionError("corrupt"), 415, "UNSUPPORTED_MEDIA"),
        (MultimodalNotConfiguredError("no model"), 409, "MULTIMODAL_NOT_CONFIGURED"),
    ],
)
def test_extract_error_mapping(exc, status, code):
    uc = MagicMock()
    uc.run = AsyncMock(side_effect=exc)
    r = _client(extraction=uc).post(
        f"{BASE}/extract", files={"file": ("s.pdf", b"%PDF", "application/pdf")}
    )
    assert r.status_code == status and r.json()["detail"]["code"] == code


def test_extract_rejects_docx_extension_and_oversize_before_use_case():
    uc = MagicMock()
    uc.run = AsyncMock()
    c = _client(extraction=uc)
    r = c.post(
        f"{BASE}/extract", files={"file": ("s.docx", b"x", "application/octet-stream")}
    )
    assert r.status_code == 415
    big = b"0" * (30 * 1024 * 1024 + 1)
    r = c.post(f"{BASE}/extract", files={"file": ("s.pdf", big, "application/pdf")})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"
    uc.run.assert_not_awaited()


# ── create / get / list / update / delete / asset / fonts / options ──────────


def test_create_decodes_assets_and_returns_201():
    admin = MagicMock()
    admin.create = AsyncMock(return_value=_bp())
    body = {
        "draft": _payload(_bp()),
        "assets": [{"id": "a1", "data_b64": base64.b64encode(PNG).decode()}],
    }
    r = _client(admin=admin).post(BASE, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "b1" and r.json()["created_at"]
    bp_arg, assets_arg, by = admin.create.await_args.args
    assert bp_arg.name == "샘플" and assets_arg == {"a1": PNG} and by == "7"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["patterns"][0]["slots"][0]["box"].update(x=1.2),
        lambda d: d["patterns"].append(dict(d["patterns"][0])),
        lambda d: d["narrative"]["sections"][0].update(pattern_ids=["nope"]),
        lambda d: d.update(extra_field=1),
    ],
)
def test_create_validation_errors_are_400(mutate):
    admin = MagicMock()
    admin.create = AsyncMock(return_value=_bp())
    d = _payload(_bp())
    mutate(d)
    r = _client(admin=admin).post(BASE, json={"draft": d, "assets": []})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_use_case_validation_error_is_400():
    admin = MagicMock()
    admin.create = AsyncMock(
        side_effect=BlueprintValidationError("asset 'a1' has no data")
    )
    r = _client(admin=admin).post(BASE, json={"draft": _payload(_bp()), "assets": []})
    assert r.status_code == 400 and "a1" in r.json()["detail"]["message"]


def test_get_list_and_not_found():
    admin = MagicMock()
    admin.get = AsyncMock(side_effect=[_bp(), BlueprintNotFoundError("x")])
    admin.list = AsyncMock(return_value=[_bp(), replace(_bp("b2"), status="inactive")])
    c = _client(admin=admin)
    assert c.get(f"{BASE}/b1").json()["patterns"][0]["id"] == "p1"
    assert c.get(f"{BASE}/zz").status_code == 404
    rows = c.get(f"{BASE}?include_inactive=true").json()
    assert [r["id"] for r in rows] == ["b1", "b2"] and rows[0]["pattern_count"] == 1
    assert admin.list.await_args.kwargs == {"include_inactive": True}


def test_update_and_delete():
    admin = MagicMock()
    admin.update = AsyncMock(return_value=replace(_bp(), name="수정"))
    admin.deactivate = AsyncMock(return_value=replace(_bp(), status="inactive"))
    c = _client(admin=admin)
    r = c.put(f"{BASE}/b1", json={"draft": _payload(_bp())})
    assert r.status_code == 200 and r.json()["name"] == "수정"
    assert admin.update.await_args.args[0] == "b1"
    assert c.delete(f"{BASE}/b1").json()["status"] == "inactive"


def test_update_not_found_and_validation():
    admin = MagicMock()
    admin.update = AsyncMock(side_effect=BlueprintNotFoundError("x"))
    c = _client(admin=admin)
    assert c.put(f"{BASE}/zz", json={"draft": _payload(_bp())}).status_code == 404
    assert c.put(f"{BASE}/b1", json={"draft": {"id": "b1"}}).status_code == 400


def test_asset_bytes_and_fonts():
    admin = MagicMock()
    admin.asset = AsyncMock(return_value=StoredAsset(_bp().assets[0], PNG))
    admin.fonts = MagicMock(return_value=MagicMock(installed=("A",), default="A"))
    c = _client(admin=admin)
    r = c.get(f"{BASE}/b1/assets/a1")
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["content-type"].startswith("image/png")
    assert c.get(f"{BASE}/fonts").json() == {"installed": ["A"], "default": "A"}


def test_non_admin_forbidden_but_options_allowed():
    admin = MagicMock()
    admin.options = AsyncMock(return_value=[("b1", "샘플")])
    c = _client(admin=admin, user=_user(UserRole.USER))
    assert c.get(BASE).status_code == 403
    assert c.get("/api/v1/blueprints/options").json() == {
        "items": [{"id": "b1", "name": "샘플"}]
    }


def test_extract_max_pages_out_of_range_is_400_not_422():
    uc = MagicMock()
    uc.run = AsyncMock()
    r = _client(extraction=uc).post(
        f"{BASE}/extract?max_pages=0",
        files={"file": ("s.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 400 and r.json()["detail"]["code"] == "VALIDATION_ERROR"
    uc.run.assert_not_awaited()


# ── blueprint-style-fidelity G6 — HTTP 레벨 v2 라운드트립 ──────────────────


def test_update_v2_payload_with_decorations_roundtrips_over_http():
    from src.domain.blueprint.value_objects import Decoration

    admin = MagicMock()
    admin.update = AsyncMock(side_effect=lambda _bid, edited: edited)
    c = _client(admin=admin)
    payload = _payload(_bp())
    payload["schema_version"] = 2
    deco = {
        "id": "deco1",
        "box": {"x": 0, "y": 0.93, "w": 1, "h": 0.07},
        "fill": "#F3F4F6",
    }
    payload["style"]["common_decorations"] = [deco]
    payload["patterns"][0]["decorations"] = [{**deco, "line": "#CCCCCC"}]
    payload["patterns"][0]["slots"][0]["align"] = "center"
    payload["style"]["header_footer"]["footer_box"] = {
        "x": 0.06,
        "y": 0.95,
        "w": 0.5,
        "h": 0.04,
    }
    r = c.put(f"{BASE}/b1", json={"draft": payload})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["style"]["common_decorations"][0]["fill"] == "#F3F4F6"
    assert body["patterns"][0]["decorations"][0]["line"] == "#CCCCCC"
    assert body["patterns"][0]["slots"][0]["align"] == "center"
    sent = admin.update.await_args.args[1]
    assert sent.patterns[0].decorations == (
        Decoration(
            "deco1", "rect", sent.patterns[0].decorations[0].box, "#F3F4F6", "#CCCCCC"
        ),
    )
    # 알 수 없는 필드는 여전히 400
    payload["patterns"][0]["slots"][0]["color"] = "#000000"
    assert c.put(f"{BASE}/b1", json={"draft": payload}).status_code == 400


# ── blueprint-font-mapping-migration §8.3 시나리오 17 — 쓰기 경계 (FR-03/04) ──


def test_payload_to_domain_normalizes_polluted_fonts():
    """관리 UI PUT 입력도 정규화를 거쳐 도메인에 들어간다."""
    from src.interfaces.schemas.blueprint import BlueprintPayload

    d = _payload(_bp())
    d["style"]["fonts"] = {
        "heading": "Malgun Gothic Bold",
        "body": "Malgun Gothic Regular",
    }
    d["font_mapping"] = {
        "Malgun Gothic Bold": "Malgun Gothic Bold",
        "Malgun Gothic Regular": "Malgun Gothic Regular",
    }

    bp = BlueprintPayload.model_validate(d).to_domain()

    assert bp.style.fonts == {"heading": "Malgun Gothic", "body": "Malgun Gothic"}
    assert bp.font_mapping == {"Malgun Gothic": "Malgun Gothic"}


def test_payload_to_domain_keeps_protected_family():
    """Plan SC-7 — API 경계에서도 실존 패밀리를 훼손하지 않는다."""
    from src.interfaces.schemas.blueprint import BlueprintPayload

    d = _payload(_bp())
    d["style"]["fonts"] = {"heading": "Times New Roman", "body": "Arial Black"}

    bp = BlueprintPayload.model_validate(d).to_domain()

    assert bp.style.fonts == {"heading": "Times New Roman", "body": "Arial Black"}


# ── blueprint-render-style-fidelity §8.2 시나리오 7 — StyleSchema 선택 필드 ──


def test_style_schema_roundtrips_new_optional_fields():
    """신규 스타일 필드가 API 응답에 포함되고 왕복에서 보존된다."""
    from dataclasses import replace as _replace

    from src.interfaces.schemas.blueprint import BlueprintPayload

    bp = _bp()
    bp = _replace(
        bp,
        style=_replace(
            bp.style,
            table_style=_replace(
                bp.style.table_style, zebra_bg="#EEEEEE", border_width_pt=0.75
            ),
            body_line_spacing=1.45,
            body_space_after_pt=33.2,
            chart_label_size_pt=9.0,
        ),
    )

    payload = _payload(bp)
    assert payload["style"]["body_line_spacing"] == 1.45
    assert payload["style"]["table_style"]["zebra_bg"] == "#EEEEEE"

    restored = BlueprintPayload.model_validate(payload).to_domain()
    assert restored.style.body_line_spacing == 1.45
    assert restored.style.chart_label_size_pt == 9.0
    assert restored.style.table_style.border_width_pt == 0.75


def test_style_schema_accepts_payload_without_new_fields():
    """기존 클라이언트가 신규 필드 없이 보내도 기본값으로 받는다."""
    from src.interfaces.schemas.blueprint import BlueprintPayload

    payload = _payload(_bp())
    for key in ("body_line_spacing", "body_space_after_pt",
                "chart_label_size_pt", "chart_label_bold"):
        payload["style"].pop(key, None)
    for key in ("zebra_bg", "border_width_pt"):
        payload["style"]["table_style"].pop(key, None)

    restored = BlueprintPayload.model_validate(payload).to_domain()

    assert restored.style.body_line_spacing == 1.0
    assert restored.style.table_style.zebra_bg == "#F3F4F6"
