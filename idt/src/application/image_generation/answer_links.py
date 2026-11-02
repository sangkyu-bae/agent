"""생성 이미지 → 답변 본문 계약 — image-generation-tool Design §3.4 / D-03.

- render_image_summary(): 워커 산출 AIMessage 본문
  (완료 안내 + 마크다운 이미지 + 다운로드 + 프롬프트)
- append_generated_images(): final_answer 가 링크를 지웠어도 본문 끝에 결정적으로
  덧붙인다. file_id 가 이미 본문에 있으면 건너뛴다. 텍스트에 남으므로 히스토리
  재조회도 동일하게 동작.
"""
from __future__ import annotations

import re

from src.domain.image_generation.value_objects import GeneratedImage

FILES_PATH_PREFIX = "/api/v1/document-extractor/files/"
_PROMPT_HEAD = 120


def image_markdown(filename: str, file_id: str) -> str:
    return f"![{filename}]({FILES_PATH_PREFIX}{file_id})"


def download_markdown(filename: str, file_id: str) -> str:
    return f"다운로드: [{filename}]({FILES_PATH_PREFIX}{file_id})"


def render_image_summary(result: GeneratedImage) -> str:
    lines = [
        f"이미지 생성 완료 ({result.filename}, {result.width}x{result.height})",
        image_markdown(result.filename, result.file_id),
        download_markdown(result.filename, result.file_id),
        f"프롬프트: {result.prompt[:_PROMPT_HEAD]}",
    ]
    if result.fell_back_to_generate:
        lines.append("(첨부 이미지가 없어 새로 생성했습니다)")
    return "\n".join(lines)


def has_inline_image(answer: str, file_id: str) -> bool:
    """`![…](/files/{file_id})` 형태의 인라인 이미지가 본문에 있는가.

    다운로드 링크(`[name](/files/{id})`)만 있고 이미지 마크다운이 없으면 False.
    2026-11 실런: final_answer 가 이미지 URL 을 `<insert-image-url-here>` 로 바꿔 쓴 채
    다운로드 링크만 남겨, file_id 포함 여부로는 유실을 잡지 못했다.
    """
    pattern = r"!\[[^\]]*\]\(" + re.escape(FILES_PATH_PREFIX + file_id) + r"\)"
    return re.search(pattern, answer or "") is not None


def append_generated_images(answer: str, images: list[dict] | None) -> str:
    """인라인 이미지가 없는 생성 이미지의 마크다운 줄을 끝에 덧붙인다 (D-03)."""
    if not images:
        return answer
    missing = [
        img for img in images
        if img.get("file_id") and not has_inline_image(answer, str(img["file_id"]))
    ]
    if not missing:
        return answer
    extra = "\n".join(
        image_markdown(str(img.get("filename") or "image.png"), str(img["file_id"]))
        for img in missing
    )
    base = (answer or "").rstrip()
    return f"{base}\n\n{extra}" if base else extra
