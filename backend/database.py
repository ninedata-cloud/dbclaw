from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    # Import all models so Base.metadata knows about them
    import backend.models.datasource  # noqa: F401
    import backend.models.host  # noqa: F401
    import backend.models.metric_snapshot  # noqa: F401
    import backend.models.diagnostic_session  # noqa: F401
    import backend.models.ai_model  # noqa: F401
    import backend.models.document  # noqa: F401
    import backend.models.user  # noqa: F401
    import backend.models.login_log  # noqa: F401
    import backend.models.report  # noqa: F401
    import backend.skills.models  # noqa: F401
    import backend.models.integration  # noqa: F401
    # Inspection models
    try:
        import backend.models.inspection_config  # noqa: F401
        import backend.models.inspection_trigger  # noqa: F401
    except ImportError:
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin user if no users exist
    from backend.models.user import User
    from backend.utils.security import hash_password
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            admin = User(
                username="admin",
                password_hash=hash_password("admin1234"),
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
