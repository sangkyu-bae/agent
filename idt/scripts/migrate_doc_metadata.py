"""Qdrant → MySQL 문서 메타데이터 역동기화 스크립트.

기존 Qdrant에 저장된 문서 포인트를 순회하며
document_metadata 테이블에 INSERT한다.
이미 존재하는 document_id는 SKIP한다.

실행: python -m scripts.migrate_doc_metadata
실행 시점: 배포 후 최초 1회 (기존 데이터 마이그레이션)
"""
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import AsyncQdrantClient

from src.config import settings
from src.domain.doc_browse.schemas import DocumentMetadata
from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository
from src.infrastructure.logging.structured_logger import StructuredLogger
from src.infrastructure.persistence.database import get_session_factory

SCROLL_BATCH = 10_000
logger = StructuredLogger("migrate_doc_metadata")


async def migrate() -> None:
    qdrant = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    session_factory = get_session_factory()

    collections = await qdrant.get_collections()
    collection_names = [c.name for c in collections.collections]
    logger.info("Collections found", count=len(collection_names))

    total_migrated = 0
    total_skipped = 0

    for col_name in collection_names:
        all_points: list = []
        next_offset = None

        while True:
            points, next_offset = await qdrant.scroll(
                collection_name=col_name,
                limit=SCROLL_BATCH,
                with_vectors=False,
                offset=next_offset,
            )
            all_points.extend(points)
            if next_offset is None:
                break

        grouped: dict[str, list] = defaultdict(list)
        for point in all_points:
            payload = point.payload or {}
            doc_id = payload.get("document_id", "unknown")
            grouped[doc_id].append(payload)

        logger.info(
            "Collection scanned",
            collection=col_name,
            total_points=len(all_points),
            unique_documents=len(grouped),
        )

        async with session_factory() as session:
            async with session.begin():
                repo = DocumentMetadataRepository(session, logger)

                for doc_id, payloads in grouped.items():
                    existing = await repo.find_by_document_id(doc_id, "migration")
                    if existing:
                        total_skipped += 1
                        continue

                    first = payloads[0]
                    chunk_types = sorted({p.get("chunk_type", "") for p in payloads})
                    strategy = "parent_child" if "parent" in chunk_types else "full_token"

                    metadata = DocumentMetadata(
                        document_id=doc_id,
                        collection_name=col_name,
                        filename=first.get("filename", "unknown"),
                        category=first.get("category", "uncategorized"),
                        user_id=first.get("user_id", ""),
                        chunk_count=len(payloads),
                        chunk_strategy=strategy,
                    )
                    await repo.save(metadata, request_id="migration")
                    total_migrated += 1

    logger.info(
        "Migration completed",
        migrated=total_migrated,
        skipped=total_skipped,
    )
    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(migrate())
