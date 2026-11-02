"""에이전트 저장 ValueError → HTTP 상태 매핑 — image-generation-tool G-I1 / G-I2.

코드 접두어(IMAGE_MODEL_INVALID / IMAGE_CONFIG_INVALID / MODEL_KIND_MISMATCH)가 붙은
메시지는 본문에 "찾을 수 없"이 들어 있어도 404 가 아니라 422 여야 한다 (Design §4.2).
"""
import pytest
from src.api.routes.agent_builder_router import save_error_http_exception

_CODED = [
    "IMAGE_MODEL_INVALID: 이미지 생성 모델을 찾을 수 없습니다: nope",
    "IMAGE_MODEL_INVALID: 'X' 은(는) 비활성 모델입니다.",
    "IMAGE_CONFIG_INVALID: image_generate 도구 워커가 없어 설정을 적용할 수 없습니다.",
    "MODEL_KIND_MISMATCH: 'GPT Image' 은(는) 이미지 생성 모델이라 "
    "대화 모델로 쓸 수 없습니다.",
]


@pytest.mark.parametrize("msg", _CODED)
def test_coded_prefixes_are_422_even_with_not_found_wording(msg: str) -> None:
    exc = save_error_http_exception(ValueError(msg))
    assert exc.status_code == 422
    assert exc.detail == msg


def _status(msg: str) -> int:
    return save_error_http_exception(ValueError(msg)).status_code


def test_legacy_mappings_unchanged() -> None:
    assert _status("LLM 모델을 찾을 수 없습니다: x") == 404
    assert _status("스킬이 이미 부착되어 있습니다") == 409
    assert _status("최대 5개까지 부착할 수 있습니다") == 409
    assert _status("지침은 비울 수 없습니다") == 422
