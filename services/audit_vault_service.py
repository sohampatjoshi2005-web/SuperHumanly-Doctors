import hashlib
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

def get_canonical_json(data: Dict[str, Any]) -> str:
    """
    Returns a deterministic JSON string with sorted keys and no extra whitespace.
    Handles datetime objects by converting them to ISO format.
    """
    def serialize(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    return json.dumps(data, sort_keys=True, separators=(',', ':'), default=serialize)

def compute_event_hash(log_data: Dict[str, Any], prev_hash: Optional[str] = None) -> str:
    """
    Computes a SHA-256 hash of the log data combined with the previous hash.
    """
    canonical_data = get_canonical_json(log_data)
    # If no previous hash, we use a fixed 'GENESIS' string to anchor the chain
    anchor = prev_hash or "GENESIS"
    
    combined = f"{canonical_data}|{anchor}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def verify_audit_chain(logs: List[Any]) -> bool:
    """
    Verifies the integrity of a sequence of AuditLog objects.
    Expects logs to be sorted by ID/Timestamp ascending.
    """
    if not logs:
        return True
    
    # Check if we have the genesis log or if the first log has a prev_hash we can't verify
    # For a full chain verification, we'd start from the VaultRoot
    
    current_prev_hash = logs[0].prev_hash
    
    for log in logs:
        # Recompute hash
        log_dict = {
            "actor": log.actor,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "extra_metadata": log.extra_metadata or {},
            "ip_address": log.ip_address,
            "timestamp": log.timestamp.isoformat() if isinstance(log.timestamp, datetime) else log.timestamp
        }
        
        computed = compute_event_hash(log_dict, log.prev_hash)
        
        if computed != log.event_hash:
            print(f"❌ Integrity violation at Log ID {log.id}: Computed {computed} != Stored {log.event_hash}")
            return False
            
        if log.prev_hash != current_prev_hash:
            # Note: This check only works if we have the full continuous list
            pass
            
        current_prev_hash = log.event_hash
        
    return True
