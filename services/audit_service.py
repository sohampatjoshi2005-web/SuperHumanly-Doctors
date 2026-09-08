"""
Batch Audit Logging Service
- Collects audit logs in Redis queue
- Flushes to PostgreSQL every 5 seconds or every 100 logs
- Reduces latency from ~5-10ms per log to <1ms
"""
import json
import logging
from datetime import datetime
from typing import Optional, List
from redis import Redis, ConnectionPool
from app.db_models import AuditLog, VaultRoot
from app.db import get_session
from app.services.audit_vault_service import compute_event_hash

logger = logging.getLogger(__name__)

from app.core.config import settings

# Redis connection pool (reused across requests)
redis_pool = None
redis_client = None

AUDIT_QUEUE_KEY = "audit_logs_queue"
QUEUE_SIZE_LIMIT = 100

def init_redis(url=None):
    """Initialize Redis connection pool from URL"""
    global redis_pool, redis_client
    try:
        redis_url = url or settings.redis_url
        redis_client = Redis.from_url(redis_url, decode_responses=True, max_connections=10)
        # Test connection
        redis_client.ping()
        logger.info(f"✓ Redis connection established for audit logging via {redis_url}")
        return True
    except Exception as e:
        logger.warning(f"⚠ Redis not available, falling back to direct PostgreSQL: {e}")
        return False


def log_audit(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    ip_address: str = "unknown",
    clinic_id: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> bool:
    """
    Synchronous audit logging (non-blocking if Redis is up, ~<1ms)
    """
    if redis_client is None:
        # Fallback: direct PostgreSQL insert if Redis unavailable
        try:
            with get_session() as session:
                from sqlmodel import select
                # Get latest hash
                stmt = select(AuditLog.event_hash).where(AuditLog.clinic_id == clinic_id).order_by(AuditLog.timestamp.desc()).limit(1)
                latest_hash = session.exec(stmt).first()
                
                if not latest_hash and clinic_id:
                    stmt_root = select(VaultRoot.genesis_hash).where(VaultRoot.clinic_id == clinic_id)
                    latest_hash = session.exec(stmt_root).first()
                
                prev_h = latest_hash or "GENESIS"
                
                now = datetime.utcnow()
                hash_input = {
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "extra_metadata": extra_metadata or {},
                    "ip_address": ip_address,
                    "timestamp": now.isoformat()
                }
                event_h = compute_event_hash(hash_input, prev_h)

                audit = AuditLog(
                    actor=actor,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    clinic_id=clinic_id,
                    ip_address=ip_address,
                    extra_metadata=extra_metadata or {},
                    timestamp=now,
                    prev_hash=prev_h,
                    event_hash=event_h
                )
                session.add(audit)
                session.commit()
            return True
        except Exception as e:
            logger.error(f"Audit log fallback failed: {e}")
            return False
    
    try:
        # Create audit log entry
        audit_entry = {
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "clinic_id": clinic_id,
            "ip_address": ip_address,
            "timestamp": datetime.utcnow().isoformat(),
            "extra_metadata": extra_metadata or {},
        }
        
        # Push to Redis queue (atomic operation, <1ms)
        queue_length = redis_client.lpush(AUDIT_QUEUE_KEY, json.dumps(audit_entry))
        
        # If queue is getting large, flush immediately
        if queue_length >= QUEUE_SIZE_LIMIT:
            flush_audit_logs_sync()
        
        return True
        
    except Exception as e:
        logger.warning(f"Audit queue failed, falling back to direct insert: {e}")
        try:
            with get_session() as session:
                from sqlmodel import select
                # Get latest hash
                stmt = select(AuditLog.event_hash).where(AuditLog.clinic_id == clinic_id).order_by(AuditLog.timestamp.desc()).limit(1)
                latest_hash = session.exec(stmt).first()
                
                if not latest_hash and clinic_id:
                    stmt_root = select(VaultRoot.genesis_hash).where(VaultRoot.clinic_id == clinic_id)
                    latest_hash = session.exec(stmt_root).first()
                
                prev_h = latest_hash or "GENESIS"
                
                now = datetime.utcnow()
                hash_input = {
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "extra_metadata": extra_metadata or {},
                    "ip_address": ip_address,
                    "timestamp": now.isoformat()
                }
                event_h = compute_event_hash(hash_input, prev_h)

                audit = AuditLog(
                    actor=actor,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    clinic_id=clinic_id,
                    ip_address=ip_address,
                    extra_metadata=extra_metadata or {},
                    timestamp=now,
                    prev_hash=prev_h,
                    event_hash=event_h
                )
                session.add(audit)
                session.commit()
            return True
        except Exception as fallback_error:
            logger.error(f"Audit log fallback also failed: {fallback_error}")
            return False


async def log_audit_batched(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    ip_address: str = "unknown",
    clinic_id: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> bool:
    """
    Queue audit log for batching (async wrapper for sync log_audit)
    """
    return log_audit(actor, action, resource_type, resource_id, ip_address, clinic_id, extra_metadata)


def flush_audit_logs_sync():
    """
    Sync operation to flush queued logs to PostgreSQL with hash-chaining.
    """
    if redis_client is None:
        return
    
    try:
        # Get all queued logs
        queue_data = redis_client.lrange(AUDIT_QUEUE_KEY, 0, -1)
        
        if not queue_data:
            return
        
        # Group entries by clinic for chaining
        clinic_groups = {}
        for entry_json in queue_data:
            try:
                entry_dict = json.loads(entry_json)
                cid = entry_dict.get("clinic_id", "GLOBAL")
                if cid not in clinic_groups:
                    clinic_groups[cid] = []
                clinic_groups[cid].append(entry_dict)
            except Exception as e:
                logger.warning(f"Invalid audit log JSON: {e}")
                continue

        with get_session() as session:
            for cid, entries in clinic_groups.items():
                # 1. Get latest hash for this clinic
                from sqlmodel import select
                stmt = select(AuditLog.event_hash).where(AuditLog.clinic_id == (cid if cid != "GLOBAL" else None)).order_by(AuditLog.timestamp.desc()).limit(1)
                latest_hash = session.exec(stmt).first()
                
                if not latest_hash and cid != "GLOBAL":
                    # Try VaultRoot
                    stmt_root = select(VaultRoot.genesis_hash).where(VaultRoot.clinic_id == cid)
                    latest_hash = session.exec(stmt_root).first()
                
                prev_h = latest_hash or "GENESIS"
                
                # 2. Compute hashes and create AuditLog objects
                for entry_dict in reversed(entries): # Redis LPUSH puts newest at 0, so we reverse for chronological order
                    # Prepare data for hashing
                    hash_input = {
                        "actor": entry_dict["actor"],
                        "action": entry_dict["action"],
                        "resource_type": entry_dict["resource_type"],
                        "resource_id": entry_dict["resource_id"],
                        "extra_metadata": entry_dict.get("extra_metadata", {}),
                        "ip_address": entry_dict["ip_address"],
                        "timestamp": entry_dict["timestamp"]
                    }
                    
                    event_h = compute_event_hash(hash_input, prev_h)
                    
                    # Create DB model
                    audit = AuditLog(
                        actor=entry_dict["actor"],
                        action=entry_dict["action"],
                        resource_type=entry_dict["resource_type"],
                        resource_id=entry_dict["resource_id"],
                        clinic_id=entry_dict["clinic_id"],
                        ip_address=entry_dict["ip_address"],
                        extra_metadata=entry_dict.get("extra_metadata", {}),
                        timestamp=datetime.fromisoformat(entry_dict["timestamp"]) if isinstance(entry_dict["timestamp"], str) else entry_dict["timestamp"],
                        prev_hash=prev_h,
                        event_hash=event_h
                    )
                    session.add(audit)
                    prev_h = event_h
            
            session.commit()
            logger.info(f"Flushed {len(queue_data)} hash-chained audit logs to PostgreSQL")
            # Clear the processed items from the queue safely
            redis_client.ltrim(AUDIT_QUEUE_KEY, len(queue_data), -1)
            
    except Exception as e:
        logger.error(f"Error flushing audit logs: {e}")


def get_redis_client() -> Optional[Redis]:
    return redis_client


def is_redis_available() -> bool:
    return redis_client is not None
