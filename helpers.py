"""
Helper functions for the email automation workflow.

These utilities are used across multiple modules.
"""

import re
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """
    Get current UTC time as an ISO 8601 string.
    
    Returns:
        str: Current time in format "YYYY-MM-DDTHH:MM:SSZ"
        
    Example:
        >>> utc_now_iso()
        '2026-05-12T14:30:45Z'
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(text: str) -> str:
    """
    Clean and normalize text by collapsing extra whitespace.
    
    This helps make downstream logic (like keyword matching) more stable
    by removing multiple spaces, tabs, and newlines.
    
    Args:
        text: Raw text to normalize
        
    Returns:
        str: Cleaned text with normalized whitespace
        
    Example:
        >>> normalize_text("Hello  \\n  world")
        'Hello world'
    """
    text = (text or "").strip()
    # Replace any sequence of whitespace with a single space
    normalized = re.sub(r"\s+", " ", text)
    return normalized


def extract_name_from_email(email: str) -> str:
    """
    Extract a friendly name from an email address.
    
    Converts "jane.customer@example.com" → "Jane Customer"
    
    Args:
        email: Email address (or fallback string)
        
    Returns:
        str: Friendly name, with fallback to "there" if email is empty
        
    Example:
        >>> extract_name_from_email("jane.customer@example.com")
        'Jane Customer'
        >>> extract_name_from_email("")
        'there'
    """
    if not email:
        return "there"
    
    # Extract the part before the @ symbol
    name_part = email.split("@", 1)[0]
    
    # Replace dots with spaces and title-case the result
    friendly_name = name_part.replace(".", " ").title()
    
    return friendly_name
