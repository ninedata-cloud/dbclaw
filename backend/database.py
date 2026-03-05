from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().debug,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    # Import all models so Base.metadata knows about them
    import backend.models.ai_model  # noqa: F401
    import backend.models.knowledge_base  # noqa: F401
    import backend.models.user  # noqa: F401
    import backend.models.login_log  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migrate: add ai_model_id to diagnostic_sessions if missing
        def _migrate(connection):
            from sqlalchemy import text, inspect
            insp = inspect(connection)
            if "diagnostic_sessions" in insp.get_table_names():
                columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]
                if "ai_model_id" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN ai_model_id INTEGER REFERENCES ai_models(id)"))
                if "kb_ids" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN kb_ids TEXT"))
                if "disabled_tools" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN disabled_tools TEXT"))

        await conn.run_sync(_migrate)

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
