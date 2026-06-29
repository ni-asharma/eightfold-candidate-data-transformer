import logging
import re
from typing import Optional
from dateutil import parser as date_parser

logger = logging.getLogger("pipeline.normalizers.dates")

# Regex to detect YYYY-MM directly
YYYY_MM_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Regex for isolated 4-digit years (e.g. "2024")
YEAR_ONLY_REGEX = re.compile(r"^\b\d{4}\b$")

def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Standardizes a date string to 'YYYY-MM' or 'Present'.
    Supported formats include 'June 2024', '06/2024', '2024-06-15', '2024', etc.
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    
    val = date_str.strip()
    if not val:
        return None
        
    # Check if ongoing employment
    if val.lower() in ["present", "current", "now", "today", "active", "ongoing"]:
        return "Present"
        
    # Fast path if already formatted properly
    if YYYY_MM_REGEX.match(val):
        return val
        
    # Handle single year (e.g. '2020' -> '2020-01')
    if YEAR_ONLY_REGEX.match(val):
        return f"{val}-01"
        
    try:
        # Parse fuzzy date
        parsed = date_parser.parse(val, fuzzy=True)
        return parsed.strftime("%Y-%m")
    except Exception as e:
        logger.warning(f"Could not parse date string '{date_str}': {e}")
        return None
