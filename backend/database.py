import logging

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import get_settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"ssl": False},
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
    import backend.models.user_session  # noqa: F401
    import backend.models.login_log  # noqa: F401
    import backend.models.report  # noqa: F401
    import backend.models.action_run  # noqa: F401
    import backend.models.system_config  # noqa: F401
    import backend.models.host_metric  # noqa: F401
    import backend.models.alert_message  # noqa: F401
    import backend.models.alert_event  # noqa: F401
    import backend.models.alert_subscription  # noqa: F401
    import backend.skills.models  # noqa: F401
    import backend.models.integration  # noqa: F401
    import backend.models.integration_bot_binding  # noqa: F401
    import backend.models.chat_channel_binding  # noqa: F401
    import backend.models.chat_event_dedup  # noqa: F401
    # Inspection models
    try:
        import backend.models.inspection_config  # noqa: F401
        import backend.models.inspection_trigger  # noqa: F401
    except ImportError:
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()

    if settings.database_url.startswith("postgresql"):
        from backend.migrations.add_soft_delete_columns import migrate as migrate_soft_delete_columns
        await migrate_soft_delete_columns()

        try:
            from backend.migrations.add_user_session_security import migrate as migrate_user_session_security
            await migrate_user_session_security()
        except Exception as exc:
            logger.warning("User session security migration failed during init_db: %s", exc)

        try:
            from backend.migrations.add_knowledge_routing_fields import migrate as migrate_knowledge_routing_fields
            await migrate_knowledge_routing_fields()
        except Exception as exc:
            logger.warning("Knowledge routing migration failed during init_db: %s", exc)

    # Seed default admin user if no users exist
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
            if not settings.initial_admin_password:
                raise RuntimeError("INITIAL_ADMIN_PASSWORD 未配置，无法初始化管理员账号")
            admin = User(
                username="admin",
                password_hash=hash_password(settings.initial_admin_password),
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
