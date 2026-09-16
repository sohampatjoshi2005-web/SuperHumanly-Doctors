from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_async_session
from app.db_models import UsageMeter
from app.db_models import User
from app.api.v1.auth import get_current_user

async def check_trial_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
) -> None:
    """
    FastAPI dependency to verify if a user's trial is still valid.
    Bypasses for unlimited users and admins.
    """
    # 1. Bypass check
    if current_user.role == "admin" or current_user.is_unlimited:
        return

    # 2. Fetch UsageMeter
    meter = await session.get(UsageMeter, str(current_user.id))
    if not meter:
        # Auto-init if missing (safety fallback)
        meter = UsageMeter(id=str(current_user.id))
        session.add(meter)
        await session.commit()
        return

    # 3. Check Usage Limit (Hard limit: 10 uses)
    if meter.usage_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial Expired"
        )

    # 4. Check Time Limit (7 days + 24h Grace Period)
    now = datetime.utcnow()
    # 8 days total = 7 days trial + 24 hours grace
    expiry_limit = meter.trial_started_at + timedelta(days=8)
    
    if now > expiry_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial Expired"
        )
