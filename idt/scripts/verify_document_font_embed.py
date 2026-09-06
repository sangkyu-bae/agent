"""E-01 PoC — 실제 MCP html_to_pdf 로 한글 폰트 임베드를 검증한다.

fix-doc-generator-korean-font Design §8.4 E-01 / Plan §5 최대 리스크:
"MCP 서버의 WeasyPrint 가 data URI @font-face 를 받아주는가?" 를 확인한다.
여기서 막히면 클라이언트 임베드 방식 전체가 무의미하므로, 코드를 믿기 전에
이 스크립트로 실경로를 한 번 통과시켜야 한다.

사용법 (MySQL·MCP 서버가 떠 있어야 함):
    python scripts/verify_document_font_embed.py <mcp_tool_id> [출력.pdf]

    mcp_tool_id 예: mcp_3f2a...  (scripts/verify_mcp_connections.py 로 조회)

판정:
    OK    — .notdef 0%, BaseFont 에 Pretendard 존재
    FAIL  — 글리프 누락 발견 (서버가 data URI 폰트를 무시했을 가능성)
    UNKNOWN — 폰트가 아예 임베드되지 않음 / 수치 판정 불가
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.infrastructure.document_extractor.document_conversion_adapter import (  # noqa: E402
    DocumentConversionAdapter,
)
from src.infrastructure.document_font.factory import (  # noqa: E402
    create_html_font_embedder,
)
from src.infrastructure.logging.structured_logger import (  # noqa: E402
    StructuredLogger,
)
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader  # noqa: E402
from src.infrastructure.mcp_registry.mcp_server_repository import (  # noqa: E402
    MCPServerRepository,
)
from src.infrastructure.persistence.database import (  # noqa: E402
    get_session_factory,
)
from tests.support.pdf_glyph_check import check_glyphs  # noqa: E402

_HTML = (
    "<h1>위기 레포트</h1>"
    "<p>자기자본비율 분석 결과를 <strong>요약</strong>합니다.</p>"
    "<table><tr><th>항목</th><td>값</td></tr></table>"
)


async def main(tool_id: str, out_path: Path) -> int:
    logger = StructuredLogger("verify-document-font-embed")
    session_factory = get_session_factory()

    async with session_factory() as session:
        adapter = DocumentConversionAdapter(
            mcp_tool_loader=MCPToolLoader(logger=logger),
            mcp_repository=MCPServerRepository(session=session, logger=logger),
            logger=logger,
            font_embedder=create_html_font_embedder(settings, logger),
        )
        pdf = await adapter.to_document(_HTML, "pdf", tool_id, "e-01")

    out_path.write_bytes(pdf)
    result = check_glyphs(pdf)

    print(f"출력: {out_path} ({len(pdf):,} bytes)")
    print(f"전략: {result.strategy}  임베드폰트: {result.base_fonts}")
    print(f".notdef: {result.notdef_codes}/{result.total_codes} ({result.ratio:.1%})")

    if not result.verifiable:
        print("UNKNOWN — 수치 판정 불가. BaseFont 목록을 눈으로 확인하세요.")
        return 2
    if result.is_broken:
        print("FAIL — 글리프 누락. 서버가 data URI @font-face 를 무시했을 수 있습니다.")
        return 1
    print("OK — 한글 글리프가 정상 임베드되었습니다.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("e01_font_poc.pdf")
    raise SystemExit(asyncio.run(main(sys.argv[1], output)))
