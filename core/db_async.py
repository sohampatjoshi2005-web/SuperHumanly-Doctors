"""
Database helper utilities
Provides wrappers for async-friendly database operations
"""
from functools import wraps
from typing import Callable, Any
from fastapi import BackgroundTasks
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.db import get_session

# Thread pool for database operations (prevents blocking event loop)
db_thread_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="db-")


async def run_sync_in_threadpool(func: Callable, *args, **kwargs) -> Any:
    """
    Run synchronous database operations in a thread pool
    This prevents blocking the FastAPI event loop
    
    Usage:
        result = await run_sync_in_threadpool(session.get, Customer, customer_id)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(db_thread_pool, func, *args)


def async_db_operation(func: Callable) -> Callable:
    """
    Decorator to automatically run sync DB operations in threadpool
    
    Usage:
        @async_db_operation
        def get_customer(customer_id):
            session = get_session()
            return session.get(Customer, customer_id)
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(db_thread_pool, lambda: func(*args, **kwargs))
    return wrapper
