import logging
from typing import Optional
import phonenumbers

logger = logging.getLogger("pipeline.normalizers.phone")

def normalize_phone(phone_str: Optional[str], default_region: str = "US") -> Optional[str]:
    """
    Normalizes a raw phone number string to E.164 format.
    Example: '1 (415) 555-0199' -> '+14155550199'
    Returns None if parsing fails or if the number is invalid.
    """
    if not phone_str:
        return None
    
    phone_clean = phone_str.strip()
    if not phone_clean:
        return None

    try:
        # If a leading '+' is present, parse directly. Otherwise, use default region.
        parsed = phonenumbers.parse(phone_clean, default_region if not phone_clean.startswith("+") else None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        else:
            logger.warning(f"Phone number '{phone_str}' is invalid in region '{default_region}'.")
            return None
    except Exception as e:
        logger.warning(f"Failed to parse phone number '{phone_str}': {e}")
        return None
