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
    import backend.models.datasource  # noqa: F401
    import backend.models.ssh_host  # noqa: F401
    import backend.models.metric_snapshot  # noqa: F401
    import backend.models.diagnostic_session  # noqa: F401
    import backend.models.ai_model  # noqa: F401
    import backend.models.knowledge_base  # noqa: F401
    import backend.models.user  # noqa: F401
    import backend.models.login_log  # noqa: F401
    import backend.skills.models  # noqa: F401
    # AI Guardian models
    import backend.models.baseline  # noqa: F401
    import backend.models.importance  # noqa: F401
    import backend.models.anomaly  # noqa: F401
    import backend.models.guardian_rule  # noqa: F401
    import backend.models.diagnostic_case  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Run migrations
        def _migrate(connection):
            from sqlalchemy import text, inspect
            from backend.migrations.rename_connection_to_datasource import migrate as rename_migration
            from backend.migrations.rename_reports_connection_to_datasource import migrate as rename_reports_migration
            from backend.migrations.rename_metrics_connection_to_datasource import migrate as rename_metrics_migration

            # Migration 1: Rename connections to datasources
            rename_migration(connection)

            # Migration 2: Rename connection_id to datasource_id in reports table
            rename_reports_migration(connection)

            # Migration 3: Rename connection_id to datasource_id in metric_snapshots table
            rename_metrics_migration(connection)

            insp = inspect(connection)

            # Migration 2: Add columns to diagnostic_sessions if missing
            if "diagnostic_sessions" in insp.get_table_names():
                columns = [c["name"] for c in insp.get_columns("diagnostic_sessions")]
                if "ai_model_id" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN ai_model_id INTEGER REFERENCES ai_models(id)"))
                if "kb_ids" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN kb_ids TEXT"))
                if "disabled_tools" not in columns:
                    connection.execute(text("ALTER TABLE diagnostic_sessions ADD COLUMN disabled_tools TEXT"))

            if "chat_messages" in insp.get_table_names():
                columns = [c["name"] for c in insp.get_columns("chat_messages")]
                if "attachments" not in columns:
                    connection.execute(text("ALTER TABLE chat_messages ADD COLUMN attachments TEXT"))

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

    # Load built-in skills
    from backend.skills.builtin_loader import load_builtin_skills

    async with async_session() as session:
        await load_builtin_skills(session)
