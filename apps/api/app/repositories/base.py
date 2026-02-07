"""Generic async CRUD base that every repository inherits from."""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepo(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def list_all(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def create_many(self, objs: list[ModelT]) -> list[ModelT]:
        self.session.add_all(objs)
        await self.session.flush()
        return objs

    async def update(self, obj: ModelT, **values: object) -> ModelT:
        for k, v in values.items():
            setattr(obj, k, v)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()
