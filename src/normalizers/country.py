import logging
from typing import Optional

logger = logging.getLogger("pipeline.normalizers.country")

# Common country and US state name mapping to ISO 3166-1 Alpha-2
COUNTRY_MAPPING = {
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "america": "US",
    "california": "US",
    "new york": "US",
    "texas": "US",
    "washington": "US",
    "ca": "US",
    "ny": "US",
    "tx": "US",
    "wa": "US",
    "india": "IN",
    "ind": "IN",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "canada": "CA",
    "can": "CA",
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "japan": "JP",
    "australia": "AU",
    "china": "CN",
    "singapore": "SG",
    "brazil": "BR",
    "brasil": "BR",
    "netherlands": "NL",
    "holland": "NL",
    "switzerland": "CH",
    "confoederatio helvetica": "CH"
}

def normalize_country(country_str: Optional[str]) -> Optional[str]:
    """
    Normalizes a country name or code string to ISO 3166-1 Alpha-2 (2 uppercase letters).
    Maps common US states (CA, NY, TX, etc.) to 'US'.
    Returns None if not recognized.
    """
    if not country_str:
        return None
        
    val = country_str.strip()
    if not val:
        return None
        
    val_lower = val.lower()
    
    # 1. Check mapping dictionary
    if val_lower in COUNTRY_MAPPING:
        return COUNTRY_MAPPING[val_lower]
        
    # 2. Check if already a valid ISO Alpha-2 code (except CA which we map to US in our mapping dictionary)
    if len(val) == 2 and val.isalpha():
        return val.upper()
        
    logger.warning(f"Could not map country '{country_str}' to ISO Alpha-2.")
    return None
