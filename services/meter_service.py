from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db_models import UsageMeter

async def increment_usage(user_id: str, session: AsyncSession) -> int:
    """
    Atomically increments the usage count for a user.
    Returns the new count.
    """
    # Use SQL atomic increment to prevent race conditions
    statement = (
        update(UsageMeter)
        .where(UsageMeter.id == user_id)
        .values(usage_count=UsageMeter.usage_count + 1)
        .returning(UsageMeter.usage_count)
    )
    result = await session.execute(statement)
    await session.commit()
    
    new_count = result.scalar_one_or_none()
    return new_count or 0
