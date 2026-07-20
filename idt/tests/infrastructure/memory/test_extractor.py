"""MemoryCandidateExtractor 단위 테스트 (agent-memory-extraction Design §3-2).

WikiDistiller 동형 — LLM은 ainvoke mock 주입, JSON 파싱·격리 검증.
"""
import json
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.memory.extractor import MemoryCandidateExtractor


def _make(response_content):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=response_content))
    logger = MagicMock()
    return MemoryCandidateExtractor(llm, logger), llm, logger


class TestExtract:
    async def test_정상_JSON_배열_파싱(self):
        extractor, _, _ = _make(json.dumps([
            {"mem_type": "profile", "content": "여신 심사팀 소속", "confidence": 80},
            {"mem_type": "preference", "content": "조문 인용 선호", "confidence": 70},
        ]))

        result = await extractor.extract("질문", "답변", [], "req-1")

        assert len(result) == 2
        assert result[0].mem_type == "profile"
        assert result[0].content == "여신 심사팀 소속"
        assert result[0].confidence == 80

    async def test_코드펜스로_감싼_JSON도_파싱(self):
        extractor, _, _ = _make(
            '```json\n[{"mem_type": "profile", "content": "내용", "confidence": 90}]\n```'
        )
        result = await extractor.extract("질문", "답변", [], "req-1")
        assert len(result) == 1

    async def test_블록_리스트_content_정규화(self):
        extractor, _, _ = _make([
            {"type": "text", "text": '[{"mem_type": "profile", "content": "내용", "confidence": 90}]'},
        ])
        result = await extractor.extract("질문", "답변", [], "req-1")
        assert len(result) == 1

    async def test_빈_배열은_빈_결과(self):
        extractor, _, _ = _make("[]")
        assert await extractor.extract("질문", "답변", [], "req-1") == []

    async def test_불량_JSON은_빈_결과와_warning(self):
        extractor, _, logger = _make("저장할 내용이 없습니다.")
        result = await extractor.extract("질문", "답변", [], "req-1")
        assert result == []
        logger.warning.assert_called_once()

    async def test_배열이_아니면_빈_결과(self):
        extractor, _, logger = _make('{"mem_type": "profile"}')
        assert await extractor.extract("질문", "답변", [], "req-1") == []
        logger.warning.assert_called_once()

    async def test_필드_누락_항목은_건너뜀(self):
        extractor, _, _ = _make(json.dumps([
            {"mem_type": "profile"},  # content 누락
            {"mem_type": "domain_term", "content": "정상", "confidence": 60},
        ]))
        result = await extractor.extract("질문", "답변", [], "req-1")
        assert len(result) == 1
        assert result[0].content == "정상"

    async def test_기존_메모리가_프롬프트에_포함(self):
        extractor, llm, _ = _make("[]")

        await extractor.extract("질문", "답변", ["여신 심사팀 소속"], "req-1")

        human_text = llm.ainvoke.call_args.args[0][1].content
        assert "여신 심사팀 소속" in human_text

    async def test_입력_절단_4000자(self):
        extractor, llm, _ = _make("[]")

        await extractor.extract("가" * 5000, "나" * 5000, [], "req-1")

        human_text = llm.ainvoke.call_args.args[0][1].content
        assert len(human_text) < 6000  # 절단 반영 (4000 + 고정 문구)
