"""ES Nori Analyzer 마이그레이션 스크립트.

기존 documents 인덱스를 nori analyzer가 적용된 새 인덱스로 마이그레이션한다.
Reindex API + Alias 전환으로 zero-downtime 마이그레이션을 수행한다.

사용법:
    python scripts/migrate_es_nori.py [--dry-run]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from elasticsearch import AsyncElasticsearch

from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig
from src.infrastructure.elasticsearch.es_index_mappings import (
    DOCUMENTS_INDEX_MAPPINGS,
    DOCUMENTS_INDEX_SETTINGS,
)


async def migrate(es: AsyncElasticsearch, index_name: str, dry_run: bool) -> None:
    new_index = f"{index_name}_v2"

    exists = await es.indices.exists(index=index_name)
    if not exists:
        print(f"[INFO] Index '{index_name}' does not exist. Creating with nori settings.")
        if not dry_run:
            await es.indices.create(
                index=index_name,
                settings=DOCUMENTS_INDEX_SETTINGS,
                mappings=DOCUMENTS_INDEX_MAPPINGS,
            )
            print(f"[OK] Index '{index_name}' created with nori analyzer.")
        return

    old_count_resp = await es.count(index=index_name)
    old_count = old_count_resp["count"]
    print(f"[INFO] Source index '{index_name}' has {old_count} documents.")

    if old_count == 0:
        print("[INFO] No documents to migrate. Recreating index with nori settings.")
        if not dry_run:
            await es.indices.delete(index=index_name)
            await es.indices.create(
                index=index_name,
                settings=DOCUMENTS_INDEX_SETTINGS,
                mappings=DOCUMENTS_INDEX_MAPPINGS,
            )
            print(f"[OK] Index '{index_name}' recreated with nori analyzer.")
        return

    new_exists = await es.indices.exists(index=new_index)
    if new_exists:
        print(f"[WARN] Target index '{new_index}' already exists. Delete it first or choose a different name.")
        return

    print(f"[STEP 1] Creating new index '{new_index}' with nori settings...")
    if not dry_run:
        await es.indices.create(
            index=new_index,
            settings=DOCUMENTS_INDEX_SETTINGS,
            mappings=DOCUMENTS_INDEX_MAPPINGS,
        )

    print(f"[STEP 2] Reindexing '{index_name}' → '{new_index}'...")
    if not dry_run:
        resp = await es.reindex(
            source={"index": index_name},
            dest={"index": new_index},
            wait_for_completion=True,
        )
        reindexed = resp.get("total", 0)
        failures = resp.get("failures", [])
        print(f"[INFO] Reindexed {reindexed} documents, {len(failures)} failures.")
        if failures:
            print(f"[WARN] Failures: {failures[:3]}")

    new_count_resp = await es.count(index=new_index) if not dry_run else {"count": old_count}
    new_count = new_count_resp["count"]
    print(f"[INFO] New index has {new_count} documents (expected {old_count}).")

    if not dry_run and new_count != old_count:
        print("[ERROR] Document count mismatch! Aborting alias switch.")
        print(f"[CLEANUP] Deleting '{new_index}'...")
        await es.indices.delete(index=new_index)
        return

    print(f"[STEP 3] Switching: delete '{index_name}', create alias '{index_name}' → '{new_index}'...")
    if not dry_run:
        await es.indices.delete(index=index_name)
        await es.indices.put_alias(index=new_index, name=index_name)

    print("[OK] Migration completed successfully.")
    if dry_run:
        print("[DRY-RUN] No changes were made.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate ES index to nori analyzer")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()

    config = ElasticsearchConfig()
    es = AsyncElasticsearch(
        hosts=[{"host": config.ES_HOST, "port": config.ES_PORT, "scheme": config.ES_SCHEME}],
        request_timeout=300,
    )

    try:
        await migrate(es, "documents", args.dry_run)
    finally:
        await es.close()


if __name__ == "__main__":
    asyncio.run(main())
