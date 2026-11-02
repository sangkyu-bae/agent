"""GenerateImageUseCase — 정책 → 어댑터 → 저장 → 원장 (Design §4.3).

Design Ref: image-generation-tool §4.3 / D-02 (DOCUMENT 저장소) / D-04 (원장 행)
- 바이트는 저장소 파일에만. 결과 VO·로그·원장에는 file_id 와 메타만 (§7).
- 원장 기록 실패는 경고 후 결과 반환 (관측성 degraded 규칙, §6.3).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.application.image_generation.registries import ImageGeneratorRegistry
from src.domain.agent_attachment.interfaces import AttachmentStoreInterface
from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.agent_run.value_objects import CostUsd, RunPurpose, TokenUsage
from src.domain.image_generation.exceptions import (
    ImageModelNotConfiguredError,
    ImageProviderError,
)
from src.domain.image_generation.interfaces import ImageGeneratorPort
from src.domain.image_generation.policies import ImageGenerationPolicy
from src.domain.image_generation.value_objects import (
    GenerateImageCommand,
    GeneratedImage,
    GenerationMode,
    ImageBytes,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.llm_model.policies import LlmModelPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GenerateImageUseCase:
    def __init__(
        self,
        registry: ImageGeneratorRegistry,
        llm_model_repo: LlmModelRepositoryInterface,
        store: AttachmentStoreInterface,
        tracker: Any,
        logger: LoggerInterface,
        *,
        max_prompt_chars: int,
        timeout_sec: float,
        max_pixels: int,
    ) -> None:
        self._registry = registry
        self._llm_model_repo = llm_model_repo
        self._store = store
        self._tracker = tracker
        self._logger = logger
        self._max_prompt_chars = max_prompt_chars
        self._timeout_sec = timeout_sec
        self._max_pixels = max_pixels
        self._last_generator: ImageGeneratorPort | None = None  # 테스트 관측용

    async def run(
        self, cmd: GenerateImageCommand, *, llm_model_id: str, run_ctx: Any
    ) -> GeneratedImage:
        prompt = ImageGenerationPolicy.validate_prompt(
            cmd.prompt, max_chars=self._max_prompt_chars
        )
        model = await self._load_image_model(llm_model_id, cmd.request_id)
        generator = self._registry.build(
            model.provider,
            llm_model=model,
            logger=self._logger,
            max_pixels=self._max_pixels,
        )
        self._last_generator = generator

        started = time.monotonic()
        image = await self._call_generator(generator, cmd, prompt)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        filename = ImageGenerationPolicy.output_filename(
            datetime.now(timezone.utc), mime=image.mime
        )
        stored = await asyncio.to_thread(
            self._store.save,
            file_bytes=image.data,
            filename=filename,
            attachment_type=AttachmentType.DOCUMENT,
            owner_user_id=cmd.owner_user_id,
            width=image.width,
            height=image.height,
        )
        result = GeneratedImage(
            file_id=stored.file_id, filename=stored.filename,
            width=image.width, height=image.height, mime=image.mime,
            model_id=model.id, model_name=model.model_name, provider=model.provider,
            prompt=prompt, mode=cmd.mode, elapsed_ms=elapsed_ms,
            fell_back_to_generate=cmd.fell_back_to_generate,
        )
        self._logger.info(
            "image generated", request_id=cmd.request_id, file_id=result.file_id,
            model_name=model.model_name, size=cmd.size.value, mode=cmd.mode.value,
            elapsed_ms=elapsed_ms, prompt_head=prompt[:80],
        )
        await self._record_ledger(model, result, run_ctx)
        return result

    async def _load_image_model(self, llm_model_id: str, request_id: str) -> LlmModel:
        model = await self._llm_model_repo.find_by_id(llm_model_id, request_id)
        if model is None:
            raise ImageModelNotConfiguredError()
        try:
            LlmModelPolicy.require_image_model(model)
        except ValueError as e:
            raise ImageModelNotConfiguredError(str(e)) from e
        return model

    async def _call_generator(
        self, generator: ImageGeneratorPort, cmd: GenerateImageCommand, prompt: str
    ) -> ImageBytes:
        if cmd.mode == GenerationMode.EDIT and cmd.source_image is not None:
            source = await asyncio.to_thread(
                Path(cmd.source_image.file_path).read_bytes
            )
            coro = generator.edit(
                prompt=prompt, source=source,
                source_mime=cmd.source_image.mime, size=cmd.size,
            )
        else:
            coro = generator.generate(prompt=prompt, size=cmd.size, quality=cmd.quality)
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout_sec)
        except asyncio.TimeoutError as e:
            raise ImageProviderError(
                f"이미지 생성이 {self._timeout_sec:.0f}초 안에 끝나지 않았습니다. "
                "다시 시도해 주세요.",
                retryable=True,
            ) from e

    async def _record_ledger(
        self, model: LlmModel, result: GeneratedImage, run_ctx: Any
    ) -> None:
        """D-04: 토큰 0·cost=장당 단가인 LLM 호출 행. run 컨텍스트가 없으면 생략."""
        if self._tracker is None or run_ctx is None:
            return
        price: Decimal | None = model.price_per_image_usd
        if price is None:
            self._logger.warning(
                "image model has no price_per_image_usd (cost recorded as 0)",
                model_id=model.id, model_name=model.model_name,
            )
        cost = CostUsd(total_usd=price if price is not None else Decimal("0"))
        try:
            await self._tracker.record_llm_call(
                run_id=run_ctx.run_id, step_id=run_ctx.step_id, tool_call_id=None,
                user_id=run_ctx.user_id, agent_id=run_ctx.agent_id,
                provider=model.provider, model_name=model.model_name,
                purpose=RunPurpose.IMAGE_GENERATION, token_usage=TokenUsage(),
                latency_ms=result.elapsed_ms, status="success",
                cost_usd_override=cost,
            )
        except Exception as e:  # 원장 실패가 결과를 막지 않는다 (§6.3)
            self._logger.warning(
                "image generation ledger record failed (best-effort)",
                exception=e, file_id=result.file_id,
            )
