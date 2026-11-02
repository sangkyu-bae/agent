"""ImageGeneratorRegistry + GenerateImageUseCase — Design §4.3 / §8.2 #4·#6·#16."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.image_generation.registries import ImageGeneratorRegistry
from src.application.image_generation.use_case import GenerateImageUseCase
from src.domain.agent_run.value_objects import RunPurpose
from src.domain.image_generation.exceptions import (
    ImageModelNotConfiguredError,
    ImageProviderError,
    InvalidImageRequestError,
    UnsupportedImageProviderError,
)
from src.domain.image_generation.value_objects import (
    GenerateImageCommand,
    GenerationMode,
    ImageBytes,
    ImageQuality,
    ImageSize,
    SourceImage,
)
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.agent_attachment.store import AgentAttachmentStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _model(kind="image", price=Decimal("0.04"), provider="openai", active=True) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="img-model", provider=provider, model_name="gpt-image-1", display_name="GPT Image",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=None, is_active=active,
        is_default=False, created_at=now, updated_at=now, model_kind=kind,
        price_per_image_usd=price,
    )


class _FakeGenerator:
    provider = "openai"

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple] = []

    async def generate(self, *, prompt, size, quality):
        self.calls.append(("generate", prompt, size, quality))
        return ImageBytes(data=PNG, width=1024, height=1024, mime="image/png")

    async def edit(self, *, prompt, source, source_mime, size):
        self.calls.append(("edit", prompt, source, source_mime, size))
        return ImageBytes(data=PNG, width=1024, height=1024, mime="image/png")


class TestRegistry:
    def test_register_supported_build(self) -> None:
        reg = ImageGeneratorRegistry()
        reg.register(_FakeGenerator, keys=("openai", "openai_compatible"))
        assert reg.supported() == ("openai", "openai_compatible")
        gen = reg.build("openai_compatible", llm_model="m", logger="l")
        assert isinstance(gen, _FakeGenerator) and gen.kwargs == {"llm_model": "m", "logger": "l"}

    def test_duplicate_raises(self) -> None:
        reg = ImageGeneratorRegistry()
        reg.register(_FakeGenerator)
        with pytest.raises(ValueError):
            reg.register(_FakeGenerator)

    def test_unknown_provider_raises(self) -> None:
        reg = ImageGeneratorRegistry()
        with pytest.raises(UnsupportedImageProviderError):
            reg.build("gemini", llm_model=None, logger=None)


def _cmd(mode=GenerationMode.GENERATE, source=None, prompt="가을 배너") -> GenerateImageCommand:
    return GenerateImageCommand(
        prompt=prompt, size=ImageSize.SQUARE_1024, quality=ImageQuality.STANDARD,
        mode=mode, source_image=source, owner_user_id="u1", request_id="r",
        fell_back_to_generate=False,
    )


def _use_case(tmp_path: Path, model=None, tracker=None, timeout=5, registry=None):
    reg = registry or ImageGeneratorRegistry()
    if registry is None:
        reg.register(_FakeGenerator, keys=("openai",))
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_model() if model is None else model)
    store = AgentAttachmentStore(str(tmp_path / "files"))
    uc = GenerateImageUseCase(
        registry=reg, llm_model_repo=repo, store=store, tracker=tracker, logger=MagicMock(),
        max_prompt_chars=200, timeout_sec=timeout, max_pixels=40_000_000,
    )
    return uc, store, reg


def _run_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.run_id.value = "run-1"
    ctx.step_id = "step-1"
    ctx.user_id = "u1"
    ctx.agent_id = "a1"
    return ctx


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_saves_document_and_returns_meta(self, tmp_path: Path) -> None:
        uc, store, _ = _use_case(tmp_path)
        out = await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)
        assert out.mime == "image/png" and (out.width, out.height) == (1024, 1024)
        assert out.filename.startswith("generated-") and out.filename.endswith(".png")
        assert out.model_id == "img-model" and out.provider == "openai"
        stored = store.load(out.file_id)
        assert stored is not None and stored.type.value == "document"
        assert stored.owner_user_id == "u1"
        assert Path(stored.file_path).read_bytes() == PNG
        assert not hasattr(out, "data")  # 바이트는 결과 VO 에 없다

    @pytest.mark.asyncio
    async def test_prompt_is_validated(self, tmp_path: Path) -> None:
        uc, _, _ = _use_case(tmp_path)
        with pytest.raises(InvalidImageRequestError):
            await uc.run(_cmd(prompt="   "), llm_model_id="img-model", run_ctx=None)

    @pytest.mark.asyncio
    async def test_chat_model_rejected(self, tmp_path: Path) -> None:
        uc, _, _ = _use_case(tmp_path, model=_model(kind="chat"))
        with pytest.raises(ImageModelNotConfiguredError):
            await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)

    @pytest.mark.asyncio
    async def test_missing_model_rejected(self, tmp_path: Path) -> None:
        uc, _, _ = _use_case(tmp_path)
        uc._llm_model_repo.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(ImageModelNotConfiguredError):
            await uc.run(_cmd(), llm_model_id="nope", run_ctx=None)

    @pytest.mark.asyncio
    async def test_unsupported_provider(self, tmp_path: Path) -> None:
        uc, _, _ = _use_case(tmp_path, model=_model(provider="gemini"))
        with pytest.raises(UnsupportedImageProviderError):
            await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)

    @pytest.mark.asyncio
    async def test_edit_reads_source_file(self, tmp_path: Path) -> None:
        src = tmp_path / "in.png"
        src.write_bytes(PNG + b"src")
        uc, _, reg = _use_case(tmp_path)
        out = await uc.run(
            _cmd(mode=GenerationMode.EDIT, source=SourceImage(file_path=str(src), mime="image/png", file_name="in.png")),
            llm_model_id="img-model", run_ctx=None,
        )
        assert out.mode == GenerationMode.EDIT
        gen = uc._last_generator
        assert gen.calls[0][0] == "edit" and gen.calls[0][2] == PNG + b"src" and gen.calls[0][3] == "image/png"

    @pytest.mark.asyncio
    async def test_timeout_becomes_provider_error(self, tmp_path: Path) -> None:
        class Slow(_FakeGenerator):
            async def generate(self, **kw):
                await asyncio.sleep(1)
                return await super().generate(**kw)

        reg = ImageGeneratorRegistry()
        reg.register(Slow, keys=("openai",))
        uc, _, _ = _use_case(tmp_path, timeout=0.01, registry=reg)
        with pytest.raises(ImageProviderError) as ei:
            await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)
        assert ei.value.retryable is True


class TestLedger:
    @pytest.mark.asyncio
    async def test_records_llm_call_with_image_cost(self, tmp_path: Path) -> None:
        tracker = MagicMock()
        tracker.record_llm_call = AsyncMock()
        uc, _, _ = _use_case(tmp_path, tracker=tracker)
        await uc.run(_cmd(), llm_model_id="img-model", run_ctx=_run_ctx())
        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["purpose"] == RunPurpose.IMAGE_GENERATION
        assert kwargs["token_usage"].total_tokens == 0
        assert kwargs["cost_usd_override"].total_usd == Decimal("0.04")
        assert kwargs["model_name"] == "gpt-image-1" and kwargs["provider"] == "openai"
        assert kwargs["run_id"].value == "run-1" and kwargs["step_id"] == "step-1"
        assert kwargs["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_price_records_zero_and_warns(self, tmp_path: Path) -> None:
        tracker = MagicMock()
        tracker.record_llm_call = AsyncMock()
        uc, _, _ = _use_case(tmp_path, model=_model(price=None), tracker=tracker)
        await uc.run(_cmd(), llm_model_id="img-model", run_ctx=_run_ctx())
        assert tracker.record_llm_call.await_args.kwargs["cost_usd_override"].total_usd == Decimal("0")
        uc._logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_no_run_ctx_skips_ledger(self, tmp_path: Path) -> None:
        tracker = MagicMock()
        tracker.record_llm_call = AsyncMock()
        uc, _, _ = _use_case(tmp_path, tracker=tracker)
        await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)
        tracker.record_llm_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ledger_failure_does_not_break_result(self, tmp_path: Path) -> None:
        tracker = MagicMock()
        tracker.record_llm_call = AsyncMock(side_effect=RuntimeError("db down"))
        uc, _, _ = _use_case(tmp_path, tracker=tracker)
        out = await uc.run(_cmd(), llm_model_id="img-model", run_ctx=_run_ctx())
        assert out.file_id


class TestNoLeak:
    @pytest.mark.asyncio
    async def test_result_serialization_has_no_bytes(self, tmp_path: Path) -> None:
        from dataclasses import asdict

        uc, _, _ = _use_case(tmp_path)
        out = await uc.run(_cmd(), llm_model_id="img-model", run_ctx=None)
        text = str(asdict(out))
        assert "PNG" not in text and "base64" not in text
