from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

SessionPrimary = async_sessionmaker(class_=AsyncSession, autobegin=False)
ReadSession = async_sessionmaker(class_=AsyncSession, autobegin=False)
