"""OpenAIImageGenerator — OpenAI 이미지 API(gpt-image 계열·dall-e) 어댑터.

Design Ref: image-generation-tool §4.3 / D-06 / D-07
- 정책 VO 의 추상 size/quality 를 모델명으로 번역한다:
  gpt-image: quality low/medium/high, 응답은 항상 b64_json
  dall-e-3 : quality standard/hd, response_format="b64_json" 명시
  dall-e-2 : quality 인자 없음
- 429/5xx/타임아웃 1회 재시도(지수 백오프). 정책 위반(400 content_policy)은 재시도 없이
  사용자 안내로 변환한다.
- API 키는 llm_model.api_key_env 가 가리키는 환경변수에서만 읽는다(로그 금지).
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
from collections.abc import Callable
from typing import Any

import openai
from PIL import Image, UnidentifiedImageError

from src.domain.image_generation.exceptions import (
    ImageModelNotConfiguredError,
    ImageProviderError,
)
from src.domain.image_generation.value_objects import (
    ImageBytes,
    ImageQuality,
    ImageSize,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_GPT_IMAGE_QUALITY = {ImageQuality.STANDARD: "medium", ImageQuality.HD: "high"}
_DALLE3_QUALITY = {ImageQuality.STANDARD: "standard", ImageQuality.HD: "hd"}
_MIME_BY_FORMAT = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_POLICY_HINTS = ("content_policy", "safety system", "moderation")


def quality_param(model_name: str, quality: ImageQuality) -> str | None:
    """모델명 → provider quality 인자. 모르면 None(인자 생략) (D-07)."""
    name = model_name.lower()
    if name.startswith("gpt-image"):
        return _GPT_IMAGE_QUALITY[quality]
    if name.startswith("dall-e-3"):
        return _DALLE3_QUALITY[quality]
    return None


def _provider_message(e: Exception, limit: int = 200) -> str:
    """OpenAI 오류 본문에서 사람이 읽을 메시지만 뽑는다 (키·본문 바이트 미포함)."""
    body = getattr(e, "body", None)
    msg = ""
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        msg = str(inner.get("message") or "")
    if not msg:
        msg = str(getattr(e, "message", "") or e)
    return msg.strip()[:limit]


class OpenAIImageGenerator:
    provider = "openai"

    def __init__(
        self,
        *,
        llm_model: LlmModel,
        logger: LoggerInterface,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        max_pixels: int = 40_000_000,
        retry_delay_sec: float = 1.0,
    ) -> None:
        self._model = llm_model
        self._logger = logger
        self._max_pixels = max_pixels
        self._retry_delay_sec = retry_delay_sec
        self._client = client or self._make_client(client_factory or openai.AsyncOpenAI)

    def _make_client(self, factory: Callable[..., Any]) -> Any:
        api_key = os.environ.get(self._model.api_key_env or "")
        if not api_key:
            raise ImageModelNotConfiguredError(
                f"환경변수 {self._model.api_key_env!r} 에 API 키가 없습니다."
            )
        return factory(api_key=api_key, base_url=self._model.base_url or None)

    async def generate(
        self, *, prompt: str, size: ImageSize, quality: ImageQuality
    ) -> ImageBytes:
        params: dict[str, Any] = {
            "model": self._model.model_name,
            "prompt": prompt,
            "size": size.value,
            "n": 1,
        }
        q = quality_param(self._model.model_name, quality)
        if q is not None:
            params["quality"] = q
        # response_format 은 보내지 않는다 — 2026-11 실측에서 Images API 가
        # unknown_parameter(400)로 거부. gpt-image 계열은 항상 b64_json 을 돌려준다.
        resp = await self._with_retry(lambda: self._client.images.generate(**params))
        return self._decode(resp)

    async def edit(
        self, *, prompt: str, source: bytes, source_mime: str, size: ImageSize
    ) -> ImageBytes:
        params: dict[str, Any] = {
            "model": self._model.model_name,
            "image": ("source.png", source, source_mime),
            "prompt": prompt, "size": size.value, "n": 1,
        }
        resp = await self._with_retry(lambda: self._client.images.edit(**params))
        return self._decode(resp)

    async def _with_retry(self, call: Callable[[], Any]) -> Any:
        for attempt in (1, 2):
            try:
                return await call()
            except openai.BadRequestError as e:
                raise self._translate_bad_request(e) from e
            except (
                openai.RateLimitError,
                openai.InternalServerError,
                openai.APITimeoutError,
                openai.APIConnectionError,
            ) as e:
                if attempt == 2:
                    raise ImageProviderError(
                        "이미지 생성 서비스가 일시적으로 응답하지 않습니다. "
                        "잠시 후 다시 시도해 주세요.",
                        retryable=True,
                    ) from e
                self._logger.warning(
                    "image generation transient error, retrying once",
                    exception=e, model_name=self._model.model_name,
                )
                await asyncio.sleep(self._retry_delay_sec)
            except openai.APIError as e:
                raise ImageProviderError(
                    f"이미지 생성 요청이 거부되었습니다: {e.__class__.__name__}",
                    retryable=False,
                ) from e
        raise AssertionError("unreachable")

    def _translate_bad_request(self, e: openai.BadRequestError) -> ImageProviderError:
        provider_msg = _provider_message(e)
        # 원인(모델 미접근·파라미터 오류)을 로그와 안내문 양쪽에 남긴다.
        # 2026-11 실측: 미인증 조직의 gpt-image-1 은 400 "does not exist" 로 거부됐다.
        self._logger.warning(
            "image generation bad request",
            model_name=self._model.model_name, provider_message=provider_msg,
        )
        text = f"{e} {getattr(e, 'body', '')}".lower()
        if any(h in text for h in _POLICY_HINTS):
            return ImageProviderError(
                "요청이 이미지 생성 정책에 걸려 거부되었습니다. "
                "표현을 바꿔 다시 요청해 주세요.",
                retryable=False,
            )
        detail = provider_msg or "크기·모델·프롬프트를 확인해 주세요."
        name = self._model.model_name
        return ImageProviderError(
            f"이미지 생성 요청이 거부되었습니다 (모델 {name}): {detail}",
            retryable=False,
        )

    def _decode(self, resp: Any) -> ImageBytes:
        data = getattr(resp, "data", None) or []
        b64 = getattr(data[0], "b64_json", None) if data else None
        if not b64:
            raise ImageProviderError(
                "이미지 생성 응답에 이미지 데이터가 없습니다 "
                "(URL 응답은 지원하지 않습니다).",
                retryable=False,
            )
        raw = base64.b64decode(b64)
        prev = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = self._max_pixels
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                fmt, (w, h) = im.format or "", im.size
        except (
            UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError,
        ) as e:
            raise ImageProviderError(
                "이미지 생성 응답을 읽을 수 없습니다.", retryable=True,
            ) from e
        finally:
            Image.MAX_IMAGE_PIXELS = prev
        return ImageBytes(
            data=raw, width=w, height=h, mime=_MIME_BY_FORMAT.get(fmt, "image/png"),
        )
