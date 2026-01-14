from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from core.env_config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    # 1. 尝试创建数据库 (如果不存在)
    # 解析 DATABASE_URL 以获取基础连接信息 (去除数据库名)
    # 假设 URL 格式: mysql+aiomysql://user:pass@host:port/dbname?params
    db_url = settings.DATABASE_URL
    if "mysql" in db_url:
        try:
            from sqlalchemy import make_url
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            
            url_obj = make_url(db_url)
            db_name = url_obj.database
            # 构建连接到 'mysql' 系统库的 URL
            # 替换 database 为 'mysql' (或者留空，视驱动而定，这里用 mysql 系统库较稳)
            system_url = url_obj.set(database="mysql")
            
            temp_engine = create_async_engine(system_url)
            async with temp_engine.connect() as conn:
                # 检查数据库是否存在
                await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                print(f"[DB] Database '{db_name}' ensured.")
            await temp_engine.dispose()
        except Exception as e:
            print(f"[WARN] Failed to auto-create database: {e}. Please ensure database exists manually.")

    from modules.digital_twin.models import RobotModel

    _ = RobotModel
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session():
    async with SessionLocal() as session:
        yield session
