"""Timeframe string parser and formatter for arbitrary interval aggregations.

Supports seconds (s), minutes (m), hours (h), and days (d).
Examples:
    "45s" -> 45
    "3m"  -> 180
    "7m"  -> 420
    "12m" -> 720
    "45m" -> 2700
    "2h"  -> 7200
    "1d"  -> 86400
"""

from __future__ import annotations
import re

_TF_REGEX = re.compile(r"^\s*(\d+)\s*([sS|mM|hH|dD]?)\s*$")

def parse_timeframe(tf_str: str) -> int:
    """Parse a timeframe string into total integer seconds.
    
    If no unit is specified (e.g. "5"), minutes are assumed.
    Returns default of 60 seconds if invalid.
    """
    if not tf_str or not isinstance(tf_str, str):
        return 60
    
    m = _TF_REGEX.match(tf_str)
    if not m:
        return 60
    
    val_str, unit_str = m.groups()
    val = int(val_str)
    if val <= 0:
        return 60
    
    unit = unit_str.lower() if unit_str else "m"
    if unit == "s":
        return val
    elif unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return val * 60

def format_timeframe(seconds: int) -> str:
    """Format integer seconds into clean timeframe text (e.g. 420 -> "7m", 7200 -> "2h")."""
    if seconds <= 0:
        return "1m"
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"
