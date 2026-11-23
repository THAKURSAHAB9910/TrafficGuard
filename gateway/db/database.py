import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from gateway.config import settings
from gateway.db.models import Base

logger = logging.getLogger("trafficguard.db")

engine = None
AsyncSessionLocal = None


async def init_db():
    global engine, AsyncSessionLocal

    # Attempt primary database (PostgreSQL)
    primary_url = settings.DATABASE_URL
    fallback_url = settings.SQLITE_FALLBACK_URL

    for url in [primary_url, fallback_url]:
        try:
            logger.info(f"Connecting to database at {url.split('@')[-1]}...")
            connect_args = {"timeout": 1.0} if "postgresql" in url else {}
            test_engine = create_async_engine(
                url,
                echo=False,
                future=True,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            engine = test_engine
            AsyncSessionLocal = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            logger.info(f"Successfully connected to database: {url.split('@')[-1]}")
            return
        except Exception as e:
            logger.warning(f"Database connection failed for {url}: {e}")
            if url == fallback_url:
                logger.error("All database connections failed. Database features may be limited.")
                raise e


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        await init_db()
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
