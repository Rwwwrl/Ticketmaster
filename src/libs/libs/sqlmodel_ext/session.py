from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

Session = async_sessionmaker(class_=AsyncSession, autobegin=False)
