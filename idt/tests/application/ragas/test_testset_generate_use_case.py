"""TestsetGenerateUseCase — 문서→QA 초안 생성 (eval-hub Design A6)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ragas.testset_generate_use_case import TestsetGenerateUseCase


def _uc(
    extractor=None,
    generator=None,
    max_input_chars=100,
    max_pairs=5,
    max_file_bytes=1024,
):
    if extractor is None:
        extractor = MagicMock(return_value="본문 " * 100)  # 400자
    if generator is None:
        generator = MagicMock()
        generator.generate = AsyncMock(
            return_value=[{"question": "q1", "ground_truth": "a1"}]
        )
    return TestsetGenerateUseCase(
        text_extractor=extractor,
        qa_generator=generator,
        logger=MagicMock(),
        max_input_chars=max_input_chars,
        max_pairs=max_pairs,
        max_file_bytes=max_file_bytes,
    ), extractor, generator


class TestGenerate:
    @pytest.mark.asyncio
    async def test_draft_반환_저장없음(self):
        uc, _, generator = _uc()
        draft = await uc.execute(b"pdf-bytes", "doc.pdf", 3, "rid")
        assert draft.source_filename == "doc.pdf"
        assert draft.items == [{"question": "q1", "ground_truth": "a1"}]

    @pytest.mark.asyncio
    async def test_입력_텍스트_상한_절단(self):
        uc, _, generator = _uc(max_input_chars=100)
        await uc.execute(b"x", "doc.pdf", 3, "rid")
        sent_text = generator.generate.await_args.kwargs["text"]
        assert len(sent_text) <= 100

    @pytest.mark.asyncio
    async def test_max_pairs_상한_적용(self):
        uc, _, generator = _uc(max_pairs=5)
        await uc.execute(b"x", "doc.pdf", 50, "rid")
        assert generator.generate.await_args.kwargs["max_pairs"] == 5

    @pytest.mark.asyncio
    async def test_빈_텍스트면_ValueError(self):
        extractor = MagicMock(return_value="   ")
        uc, _, _ = _uc(extractor=extractor)
        with pytest.raises(ValueError):
            await uc.execute(b"x", "doc.pdf", 3, "rid")

    @pytest.mark.asyncio
    async def test_미지원_확장자_ValueError(self):
        extractor = MagicMock(side_effect=ValueError("지원하지 않는 형식"))
        uc, _, _ = _uc(extractor=extractor)
        with pytest.raises(ValueError):
            await uc.execute(b"x", "doc.hwp", 3, "rid")

    @pytest.mark.asyncio
    async def test_파일_크기_상한_초과_ValueError(self):
        uc, extractor, _ = _uc(max_file_bytes=10)
        with pytest.raises(ValueError, match="너무 큽"):
            await uc.execute(b"x" * 11, "doc.pdf", 3, "rid")
        extractor.assert_not_called()  # 파싱 전에 차단
