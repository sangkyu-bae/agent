from qdrant_client import AsyncQdrantClient, models

from src.domain.collection.interfaces import CollectionRepositoryInterface
from src.domain.collection.schemas import (
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
)


class QdrantCollectionRepository(CollectionRepositoryInterface):
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def list_collections(self) -> list[CollectionInfo]:
        result = await self._client.get_collections()
        infos: list[CollectionInfo] = []
        for c in result.collections:
            detail = await self._client.get_collection(c.name)
            infos.append(
                CollectionInfo(
                    name=c.name,
                    vectors_count=detail.indexed_vectors_count or 0,
                    points_count=detail.points_count or 0,
                    status=detail.status.value if detail.status else "unknown",
                )
            )
        return infos

    async def get_collection(self, name: str) -> CollectionDetail | None:
        if not await self._client.collection_exists(name):
            return None
        detail = await self._client.get_collection(name)
        params = detail.config.params
        return CollectionDetail(
            name=name,
            vectors_count=detail.indexed_vectors_count or 0,
            points_count=detail.points_count or 0,
            status=detail.status.value if detail.status else "unknown",
            vector_size=params.vectors.size,
            distance=params.vectors.distance.value,
        )

    async def create_collection(self, req: CreateCollectionRequest) -> None:
        await self._client.create_collection(
            collection_name=req.name,
            vectors_config=models.VectorParams(
                size=req.vector_size,
                distance=getattr(models.Distance, req.distance.name),
            ),
        )

    async def delete_collection(self, name: str) -> None:
        await self._client.delete_collection(name)

    async def collection_exists(self, name: str) -> bool:
        return await self._client.collection_exists(name)

    async def update_collection_alias(
        self, old_name: str, new_alias: str
    ) -> None:
        await self._client.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=old_name,
                        alias_name=new_alias,
                    )
                ),
            ]
        )
