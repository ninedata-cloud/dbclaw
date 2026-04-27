from sqlalchemy import Boolean, Column, DateTime, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.datetime_helper import now


class SoftDeleteMixin:
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, nullable=True)

    def soft_delete(self, user_id: int | None = None) -> None:
        self.is_deleted = True
        self.deleted_at = now()
        self.deleted_by = user_id

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None


def alive_filter(model):
    return model.is_deleted == False


def alive_select(model):
    return select(model).where(alive_filter(model))


async def get_alive_by_id(db: AsyncSession, model, object_id: int):
    result = await db.execute(
        select(model).where(model.id == object_id, alive_filter(model))
    )
    return result.scalar_one_or_none()
