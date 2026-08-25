"""기존 블루프린트를 같은 id 로 재추출한다 (blueprint-style-fidelity §4.4).

사용:
    python -m scripts.blueprint_reextract --id <blueprint_id> --file <pdf|pptx> \
        [--max-pages 20]

- 프로덕션과 같은 코드 경로(BlueprintAdminUseCase.reextract) 를 탄다.
- 비전 모델은 DB 의 multimodal_setting 을 사용한다 (미설정 시 409 와 같은 예외).
- 트랜잭션 경계는 이 스크립트가 가진다 (repository 는 commit 하지 않는다).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # main.py 와 동일 — multimodal 의 api_key_env 는 os.environ 에서 읽는다

from src.api.blueprint_di import build_admin_use_case  # noqa: E402
from src.config import settings  # noqa: E402
from src.infrastructure.llm.llm_factory import LLMFactory  # noqa: E402
from src.infrastructure.logging import StructuredLogger  # noqa: E402
from src.infrastructure.persistence.database import (  # noqa: E402
    get_session_factory,
)


async def _run(blueprint_id: str, file: Path, max_pages: int) -> int:
    logger = StructuredLogger(name="blueprint-reextract")
    request_id = f"reextract-{uuid.uuid4().hex[:8]}"
    factory = get_session_factory()
    async with factory() as session:
        use_case = build_admin_use_case(
            session, llm_factory=LLMFactory(), logger=logger, settings=settings
        )
        async with session.begin():
            bp = await use_case.reextract(
                blueprint_id, file.read_bytes(), file.name, max_pages, request_id
            )
    logger.info(
        "reextract done",
        blueprint_id=bp.id,
        schema_version=bp.schema_version,
        patterns=len(bp.patterns),
        assets=len(bp.assets),
        common_decorations=len(bp.style.common_decorations),
        footer_text=bp.style.header_footer.footer_text,
        fonts=bp.style.fonts,
    )
    for warning in bp.warnings:
        logger.warning("reextract warning", detail=warning)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="blueprint 재추출 (같은 id 덮어쓰기)")
    parser.add_argument("--id", required=True, help="document_blueprint.id")
    parser.add_argument("--file", required=True, type=Path, help="골든 샘플 pdf/pptx")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.file.is_file():
        parser.error(f"file not found: {args.file}")
    return asyncio.run(_run(args.id, args.file, args.max_pages))


if __name__ == "__main__":
    sys.exit(main())
