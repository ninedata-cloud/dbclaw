import logging

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _create_engine():
    settings = get_settings()
    if not settings.database_url.startswith(("postgresql", "postgres")):
        raise RuntimeError("元数据库仅支持 PostgreSQL，请检查 DATABASE_URL 配置。")

    connect_args = {"ssl": False}
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _session_factory


class _LazyAsyncEngineProxy:
    def __getattr__(self, name):
        return getattr(get_engine(), name)

    def __repr__(self):
        return repr(get_engine())


class _LazyAsyncSessionProxy:
    def __call__(self, *args, **kwargs):
        return get_session_factory()(*args, **kwargs)


engine = _LazyAsyncEngineProxy()
async_engine = engine
async_session = _LazyAsyncSessionProxy()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    # Import the model package once so Base.metadata picks up every table definition.
    import backend.models  # noqa: F401

    from backend.migrations.runner import run_post_create_migrations, run_pre_create_migrations

    await run_pre_create_migrations()

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await run_post_create_migrations()

    settings = get_settings()

    # Seed default admin user if no user exist
    from backend.models.user import User
    from backend.models.soft_delete import alive_filter
    from backend.utils.security import hash_password
    from sqlalchemy import select

    if settings.encryption_key == "temporary-encryption-key":
        raise RuntimeError("ENCRYPTION_KEY 未配置，拒绝使用默认加密密钥启动")
    if settings.public_share_secret_key == "change-me-to-a-random-public-share-secret":
        raise RuntimeError("PUBLIC_SHARE_SECRET_KEY 未配置，拒绝使用默认分享密钥启动")

    async with async_session() as session:
        result = await session.execute(select(User).where(alive_filter(User)).limit(1))
        if result.scalar_one_or_none() is None:
            admin_password = settings.initial_admin_password or "admin1234"
            if admin_password == "admin1234":
                logger.warning("Using default initial admin password 'admin1234'; change it after first login.")
            admin = User(
                username="admin",
                password_hash=hash_password(admin_password),
                display_name="Administrator",
                is_active=True,
                is_admin=True,
            )
            session.add(admin)
            await session.commit()

    # Load built-in skills
    from backend.skills.builtin_loader import load_builtin_skills

    async with async_session() as session:
        await load_builtin_skills(session)

    from backend.services.builtin_docs.seeder import seed_builtin_docs
    async with async_session() as session:
        await seed_builtin_docs(session)

    from backend.services.document_service import backfill_document_compilation
    async with async_session() as session:
        updated = await backfill_document_compilation(session)
        if updated:
            logger.info("Backfilled knowledge compilation for %s documents", updated)
