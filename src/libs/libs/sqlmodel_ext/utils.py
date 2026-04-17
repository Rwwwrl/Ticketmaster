from sqlalchemy import text

from libs.sqlmodel_ext.session import Session


async def health_check() -> None:
    """Verify database connectivity by executing SELECT 1."""
    async with Session() as session, session.begin():
        await session.execute(text("SELECT 1"))
