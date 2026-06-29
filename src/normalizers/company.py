import logging
import re
from typing import Optional

logger = logging.getLogger("pipeline.normalizers.company")

# Comprehensive suffix matchers (case-insensitive, matched at end of string)
SUFFIX_PATTERNS = [
    r"\bprivate\s+limited\b",
    r"\bpvt\s+ltd\b",
    r"\bcorporation\b",
    r"\bcorp\b",
    r"\binc\b",
    r"\bllc\b",
    r"\bltd\b",
    r"\blimited\b",
    r"\bpvt\b",
    r"\bco\b",
    r"\bsa\b",
    r"\bgmbh\b",
    r"\bag\b",
    r"\bplc\b"
]

# Compile patterns to match suffixes optionally followed by a period at the end of the string
COMPILED_PATTERNS = [
    re.compile(rf"\b{p}\.?$", re.IGNORECASE) for p in SUFFIX_PATTERNS
]

def capitalize_word(w: str) -> str:
    """
    Capitalizes a company word. Keeps common domain extensions (.com, .org, .ai) lowercase.
    """
    if not w:
        return ""
    if "." in w:
        parts = w.split(".")
        parts[0] = parts[0].capitalize()
        for idx in range(1, len(parts)):
            ext = parts[idx].lower()
            if ext in ["com", "org", "net", "edu", "gov", "ai", "io"]:
                parts[idx] = ext
            else:
                parts[idx] = parts[idx].capitalize()
        return ".".join(parts)
    return w.capitalize()

def normalize_company(company_str: Optional[str]) -> Optional[str]:
    """
    Cleans corporate suffixes (recursively handling multiple suffixes like 'Pvt. Ltd.')
    and standardizes casing while keeping domains clean.
    Example: 'ACME Pvt. Ltd.' -> 'Acme', 'Eightfold AI LLC' -> 'Eightfold AI'
    """
    if not company_str:
        return None
        
    cleaned = company_str.strip()
    if not cleaned:
        return None

    prev = ""
    while prev != cleaned:
        prev = cleaned
        # Strip trailing commas, periods, or spaces
        cleaned = re.sub(r"[,\s.]+$", "", cleaned).strip()
        
        # Check and strip matches sequentially
        for pattern in COMPILED_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                cleaned = cleaned[:match.start()].strip()
                break  # Restart loop to check for further suffixes

    # Strip any remaining trailing formatting marks
    cleaned = re.sub(r"[,\s.]+$", "", cleaned).strip()
    
    if not cleaned:
        return None
        
    # Standardize casing if all uppercase or all lowercase
    if cleaned.isupper() or cleaned.islower():
        words = cleaned.split()
        cleaned = " ".join(capitalize_word(w) for w in words)
        
    return cleaned
