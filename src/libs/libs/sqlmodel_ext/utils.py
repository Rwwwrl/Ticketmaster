from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession


async def health_check(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Verify database connectivity by executing SELECT 1 through the given sessionmaker."""
    async with session_maker() as session, session.begin():
        await session.execute(text("SELECT 1"))
