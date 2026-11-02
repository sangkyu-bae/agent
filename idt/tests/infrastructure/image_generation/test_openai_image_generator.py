"""OpenAIImageGenerator — Design §4.3 / D-07 / §8.2 #5 (AsyncOpenAI 모킹)."""
import base64
import io
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from src.domain.image_generation.exceptions import (
    ImageModelNotConfiguredError,
    ImageProviderError,
)
from src.domain.image_generation.value_objects import ImageQuality, ImageSize
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.image_generation.openai_image_generator import (
    OpenAIImageGenerator,
    quality_param,
)


def _png_b64(w=8, h=4) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _model(name="gpt-image-1", base_url=None, env="OPENAI_API_KEY") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m", provider="openai", model_name=name, display_name=name, description=None,
        api_key_env=env, max_tokens=None, is_active=True, is_default=False,
        created_at=now, updated_at=now, model_kind="image", base_url=base_url,
    )


def _client(b64=None, side_effect=None) -> MagicMock:
    client = MagicMock()
    resp = SimpleNamespace(data=[SimpleNamespace(b64_json=b64 or _png_b64(), url=None)])
    client.images.generate = AsyncMock(return_value=resp, side_effect=side_effect)
    client.images.edit = AsyncMock(return_value=resp)
    return client


class TestParamMapping:
    @pytest.mark.parametrize(
        ("model", "q", "expected"),
        [
            ("gpt-image-1", ImageQuality.STANDARD, "medium"),
            ("gpt-image-1", ImageQuality.HD, "high"),
            ("gpt-image-1-mini", ImageQuality.HD, "high"),
            ("dall-e-3", ImageQuality.STANDARD, "standard"),
            ("dall-e-3", ImageQuality.HD, "hd"),
            ("dall-e-2", ImageQuality.HD, None),
            ("some-custom-image", ImageQuality.HD, None),
        ],
    )
    def test_quality_param(self, model, q, expected) -> None:
        assert quality_param(model, q) == expected



class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_calls_sdk_and_decodes(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        client = _client(_png_b64(8, 4))
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client)
        out = await gen.generate(prompt="p", size=ImageSize.LANDSCAPE_1536, quality=ImageQuality.HD)
        kwargs = client.images.generate.await_args.kwargs
        assert kwargs == {"model": "gpt-image-1", "prompt": "p", "size": "1536x1024", "n": 1, "quality": "high"}
        assert (out.width, out.height, out.mime) == (8, 4, "image/png")
        assert out.data.startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_dalle3_never_sends_response_format(self, monkeypatch) -> None:
        # 2026-11 실측: Images API 가 response_format 을 unknown_parameter 로 거부한다.
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        client = _client()
        gen = OpenAIImageGenerator(llm_model=_model("dall-e-3"), logger=MagicMock(), client=client)
        await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)
        kwargs = client.images.generate.await_args.kwargs
        assert "response_format" not in kwargs and kwargs["quality"] == "standard"
        await gen.edit(prompt="e", source=b"\x89PNG", source_mime="image/png", size=ImageSize.SQUARE_1024)
        assert "response_format" not in client.images.edit.await_args.kwargs

    @pytest.mark.asyncio
    async def test_bad_request_surfaces_provider_message_and_logs(self, monkeypatch) -> None:
        # 2026-11 실측: 미인증 조직은 gpt-image-1 에 400 "does not exist" — 관리자가 원인을 알 수 있어야 한다
        import openai

        monkeypatch.setenv("OPENAI_API_KEY", "k")
        resp = MagicMock(); resp.status_code = 400; resp.headers = {}
        err = openai.BadRequestError(
            "Error code: 400", response=resp,
            body={"message": "The model 'gpt-image-1' does not exist.", "type": "image_generation_user_error",
                  "param": "model", "code": "invalid_value"},
        )
        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=err)
        logger = MagicMock()
        gen = OpenAIImageGenerator(llm_model=_model(), logger=logger, client=client, retry_delay_sec=0)
        with pytest.raises(ImageProviderError) as ei:
            await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)
        assert ei.value.retryable is False
        assert "does not exist" in ei.value.user_message
        assert "gpt-image-1" in ei.value.user_message
        logger.warning.assert_called_once()
        assert "does not exist" in str(logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_edit_passes_file_tuple(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        client = _client()
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client)
        await gen.edit(prompt="bg white", source=b"\x89PNGsrc", source_mime="image/png", size=ImageSize.SQUARE_1024)
        kwargs = client.images.edit.await_args.kwargs
        assert kwargs["model"] == "gpt-image-1" and kwargs["prompt"] == "bg white"
        assert kwargs["image"] == ("source.png", b"\x89PNGsrc", "image/png")
        assert kwargs["size"] == "1024x1024" and kwargs["n"] == 1

    @pytest.mark.asyncio
    async def test_missing_api_key_env_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("NOPE_KEY", raising=False)
        with pytest.raises(ImageModelNotConfiguredError):
            OpenAIImageGenerator(llm_model=_model(env="NOPE_KEY"), logger=MagicMock())

    @pytest.mark.asyncio
    async def test_url_only_response_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        client = MagicMock()
        client.images.generate = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(b64_json=None, url="https://x")])
        )
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client)
        with pytest.raises(ImageProviderError):
            await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)

    @pytest.mark.asyncio
    async def test_corrupt_image_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        client = _client(base64.b64encode(b"not-an-image").decode())
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client)
        with pytest.raises(ImageProviderError):
            await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)


class TestRetryAndPolicy:
    @pytest.mark.asyncio
    async def test_retries_once_on_rate_limit(self, monkeypatch) -> None:
        import openai

        monkeypatch.setenv("OPENAI_API_KEY", "k")
        resp = MagicMock(); resp.status_code = 429; resp.headers = {}
        err = openai.RateLimitError("slow down", response=resp, body=None)
        ok = SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64(), url=None)])
        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=[err, ok])
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client, retry_delay_sec=0)
        out = await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)
        assert out.width == 8 and client.images.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_second_failure_is_retryable_error(self, monkeypatch) -> None:
        import openai

        monkeypatch.setenv("OPENAI_API_KEY", "k")
        resp = MagicMock(); resp.status_code = 503; resp.headers = {}
        err = openai.InternalServerError("down", response=resp, body=None)
        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=[err, err])
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client, retry_delay_sec=0)
        with pytest.raises(ImageProviderError) as ei:
            await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)
        assert ei.value.retryable is True

    @pytest.mark.asyncio
    async def test_content_policy_is_not_retried(self, monkeypatch) -> None:
        import openai

        monkeypatch.setenv("OPENAI_API_KEY", "k")
        resp = MagicMock(); resp.status_code = 400; resp.headers = {}
        err = openai.BadRequestError(
            "Your request was rejected as a result of our safety system",
            response=resp, body={"error": {"code": "content_policy_violation"}},
        )
        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=err)
        gen = OpenAIImageGenerator(llm_model=_model(), logger=MagicMock(), client=client, retry_delay_sec=0)
        with pytest.raises(ImageProviderError) as ei:
            await gen.generate(prompt="p", size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD)
        assert ei.value.retryable is False
        assert "정책" in ei.value.user_message
        assert client.images.generate.await_count == 1

    def test_base_url_passed_to_client(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        captured = {}

        def fake_client_factory(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        OpenAIImageGenerator(
            llm_model=_model(base_url="http://local:8080/v1"), logger=MagicMock(),
            client_factory=fake_client_factory,
        )
        assert captured == {"api_key": "k", "base_url": "http://local:8080/v1"}
